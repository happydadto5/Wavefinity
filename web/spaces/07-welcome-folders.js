"use strict";

// ------------------------------------------------------------ folder choice

// Returns a real folder or null - never a pretend one. With stayOnSetup the
// caller is mid-setup, so a refusal explains itself inline instead of
// throwing the person's entered Space details away.
SP.pickFolder = async ({ stayOnSetup = false, spaceRoot = false, accessContext = null } = {}) => {
  if (state.runtime.hosted) {
    if (!window.WFFileSystem?.supportsDirectoryPicker()) {
      if (stayOnSetup) {
        SP.fail(
          "This browser cannot give Wavefinity writable folder access. Your Space details have not been changed.",
          "#space-create",
        );
      } else {
        SP.showFolderAccessNeeded("unsupported", accessContext);
      }
      return null;
    }

    const picked = await WFFileSystem.pickDirectory();
    // A cancel is silent and leaves everything as it was.
    if (!picked || picked.status === "cancelled") return null;

    if (picked.status !== "ok" || !picked.handle) {
      if (stayOnSetup) {
        SP.fail(
          "Folder access was not granted. Your Space details are still here; choose the folder again and allow read/write access.",
          "#space-create",
        );
      } else {
        SP.showFolderAccessNeeded(
          picked.status === "denied" ? "denied" : "unsupported",
          accessContext,
        );
      }
      return null;
    }

    return { handle: picked.handle, name: picked.handle.name };
  }

  const data = await api("/api/browse-output-folder", {
    current: state.output,
    space_root: Boolean(spaceRoot),
  });
  return data.folder || null;
};

// Safe for every caller (Recents, Open Existing, collision "Open this
// Space", Choose Folder, etc.): a folder that still needs its one-time
// setup pass - including a legacy box, v2/v3, or migration-needed Space -
// is never applied/opened directly; it always goes through the explicit
// setup/migration flow first - see Fix 004 Correction 9.B.
SP.afterPick = async folder => {
  if (!folder) return null;
  if (state.runtime.hosted) {
    // A hosted object with no handle is not a folder and is never adopted.
    if (!folder.handle) {
      SP.showFolderAccessNeeded("unsupported");
      return null;
    }
    const inspected = await SP.inspectHosted(folder);
    if (inspected.needs_setup) {
      SP.enterSetupFor(folder, inspected);
      return inspected;
    }
    return SP.useHostedFolder(folder, { openPreferredView: true });
  }
  const inspected = await api("/api/space/inspect", { output: folder });
  SP.recent = inspected.recent || [];
  if (inspected.folder?.needs_setup) {
    SP.enterSetupFor(folder, inspected.folder);
    return inspected.folder;
  }
  // Resolve the safe-leave decision BEFORE the backend remembers this
  // folder as active (Fix 019 correction C1.2) - Cancel or a failed save
  // must abort before /api/folder/use ever runs, so the backend's
  // remembered active folder/Space cannot get ahead of what is on screen.
  const okToLeave = await SP.leaveSpaceSafely();
  if (!okToLeave) return null;
  const data = await api("/api/folder/use", { output: folder });
  SP.recent = data.recent || [];
  // The leave decision is already resolved - clear the old Drawer state
  // exactly once, with no second prompt, then adopt the new folder.
  if (!(await SP.resetDrawer({ skipSafeLeave: true }))) return null;
  if (!(await SP.applyFolder(data.folder, { reset: false }))) return null;
  SP.close();
  if (data.folder.folder_mode === "space") {
    if (!(await SP.openTypedSpacePreferredView())) return null;
  }
  toast(data.folder.folder_mode === "space"
    ? `Opened ${data.folder.space?.name || data.folder.folder_name}.`
    : `Saving designs to ${data.folder.folder_name}.`);
  return data.folder;
};

SP.chooseFolder = () => SP.run(async () => {
  const folder = await SP.pickFolder();
  if (folder) await SP.afterPick(folder);
});

// The opt-out checkbox beside the save folder. Space always keeps inventory
// on, and a hosted session with no persistent folder has nowhere to keep one,
// so the control is disabled in both cases (see setFolderState) - these
// checks just guard against a stray change event reaching here anyway.
SP.setInventory = enabled => SP.run(async () => {
  if (!SP.hasFolder() || state.folderMode === "space") return;
  if (state.runtime.hosted && !state.browserFolder?.handle) return;
  if (state.runtime.hosted) {
    await SP.writeMetadata(state.browserFolder?.handle, "design", null, enabled);
  } else {
    await api("/api/folder/inventory", { output: state.output, inventory: enabled });
  }
  state.inventoryEnabled = enabled;
  state.keepLog = enabled;
  toast(enabled ? "Keeping inventory for this folder." : "Inventory turned off for this folder.");
});

// Fix 034 K2: Keep bin defaults is retired (New Bin is always fresh;
// Duplicate is the explicit clone workflow) - old keep_bin_defaults/
// bin_defaults/part_defaults metadata keys are still read tolerantly on
// folder load elsewhere, but nothing writes or acts on them any more.

// ------------------------------------------------------------ welcome/manage

SP.renderRecent = () => {
  const list = $("#welcome-recent");
  if (!SP.recent.length) {
    list.innerHTML = `<li class="welcome-empty">No recent folders yet.</li>`;
    return;
  }
  list.innerHTML = SP.recent.map((one, index) => {
    const unavailable = one.missing || one.invalid || one.conflict;
    const space = one.folder_mode === "space";
    const kind = SP_KINDS[one.kind];
    const meta = [one.conflict ? "duplicate Space identity" : one.invalid ? "metadata unavailable" : space ? `${kind?.label || "Space"} · SPACE` : "Design folder", one.summary_text || SP.sizeText(one.size), one.missing ? "folder not found" : ""]
      .filter(Boolean).join(" · ");
    const current = state.runtime.hosted
      ? (one.handle && state.browserFolder?.handle === one.handle ? " <em>current</em>" : "")
      : (spSame(one.folder, state.output) ? " <em>current</em>" : "");
    const folderLabel = state.runtime.hosted ? (one.folder_name || one.name) : one.folder;
    return `<li class="welcome-recent-item${unavailable ? " missing" : ""}">
      <button type="button" class="welcome-recent-open" data-index="${index}" title="${escapeHtml(folderLabel)}"${unavailable ? " disabled" : ""}>
        <span class="welcome-recent-icon" aria-hidden="true">${space ? SP.compactKindIcon(one.kind) : "📁"}</span>
        <span class="welcome-recent-text"><span><strong>${escapeHtml(one.name)}</strong>${current}</span>
          <small>${escapeHtml(meta)}</small><small>${escapeHtml(folderLabel)}</small></span>
      </button>
      <button type="button" class="welcome-recent-forget" data-forget="${index}" title="Remove from this list" aria-label="Remove ${escapeHtml(one.name)} from recent folders">✕</button>
    </li>`;
  }).join("");
};

SP.renderOtherSpaces = () => {
  document.querySelectorAll("[data-other-spaces-container]").forEach(container => {
    container.hidden = state.runtime.hosted || SP.otherSpaces.length === 0;
    const list = container.querySelector("[data-other-spaces-list]");
    list.innerHTML = SP.otherSpaces.map((one, index) => {
      const kind = SP_KINDS[one.kind];
      const meta = [kind?.label || "Space", one.summary_text || SP.sizeText(one.size)].filter(Boolean).join(" · ");
      return `<li class="welcome-recent-item"><button type="button" class="welcome-recent-open" data-other-index="${index}" title="${escapeHtml(one.folder)}">
        <span class="welcome-recent-icon" aria-hidden="true">${SP.compactKindIcon(one.kind)}</span>
        <span class="welcome-recent-text"><strong>${escapeHtml(one.name)}</strong><small>${escapeHtml(meta)}</small></span>
      </button></li>`;
    }).join("");
  });
};

SP.refreshOtherSpaces = async () => {
  if (state.runtime.hosted) return;
  try {
    SP.otherSpaces = (await api("/api/space/other-spaces", {})).other_spaces || [];
    SP.renderOtherSpaces();
  } catch (_error) {
    SP.otherSpaces = [];
    SP.renderOtherSpaces();
  }
};

SP.HOSTED_RECENT_KEY = "recent-folders-v1";

SP.loadHostedRecent = async () => {
  const rows = await WFFileSystem.load(SP.HOSTED_RECENT_KEY);
  return Array.isArray(rows)
    ? rows.filter(one => one?.handle && one.handle.kind === "directory").slice(0, 10)
    : [];
};

SP.saveHostedRecent = async rows => {
  await WFFileSystem.save(SP.HOSTED_RECENT_KEY, rows.slice(0, 10));
};

SP.sameHostedHandle = async (a, b) => {
  if (a === b) return true;
  if (!a || !b || typeof a.isSameEntry !== "function") return false;
  try { return await a.isSameEntry(b); }
  catch (_error) { return false; }
};

SP.rememberHostedRecent = async (folder, info) => {
  if (!folder?.handle) return;
  const prior = await SP.loadHostedRecent();
  const kept = [];
  for (const row of prior) {
    if (!(await SP.sameHostedHandle(row.handle, folder.handle))) kept.push(row);
  }
  const space = info?.folder_mode === "space" ? info.space : null;
  const row = {
    handle: folder.handle,
    name: space?.name || folder.name,
    folder_name: folder.name,
    folder_mode: info?.folder_mode || "design",
    space_id: info?.space_id || null,
    kind: space?.kind || null,
    size: space ? [space.x, space.y, space.z] : null,
    summary_text: info?.summary_text || "",
  };
  SP.recent = [row, ...kept].slice(0, 10);
  await SP.saveHostedRecent(SP.recent);
};

SP.welcomeOtherSpaces = () => {
  SP.renderOtherSpaces();
  if (!SP.otherSpacesFresh) void SP.refreshOtherSpaces();
  SP.otherSpacesFresh = false;
};

SP.showResume = info => {
  SP.resume = info;
  SP.showOnly("welcome-resume");
  const space = info.space || {};
  const kind = SP_KINDS[space.kind] || SP_KINDS.drawer;
  $("#welcome-resume-icon").innerHTML = SP.compactKindIcon(space.kind);
  $("#welcome-resume-name").textContent = space.name || info.folder_name;
  $("#welcome-resume-meta").textContent = [kind.label, space.kind === "storage_drawers" ? SP.storageDrawersSummaryText(space) : SP.sizeText([space.x, space.y, space.z])].filter(Boolean).join(" · ");
  $("#welcome-resume-folder").textContent = info.folder;
  $("#welcome-resume-folder").title = info.folder;
  SP.renderStorageCard();
  SP.refreshStorage();
  SP.welcomeOtherSpaces();
  SP.showDialog();
};

// An existing Space lands by its loaded Inventory, without changing its
// restored design or making a second inventory parser.
SP.openTypedSpacePreferredView = async () => {
  try {
    if (!(await DL.ensureLoaded())) return false;
  } catch (error) {
    toast(`Could not read this Space's inventory: ${error.message}`, true, 7000);
    return false;
  }
  // Fix 103 (Section F): a structural Space opens on its structural Design.
  const structuralKind = DP.structuralTargetEnabled ? DP.structuralKindFor(state.activeSpace) : null;
  if (structuralKind) {
    if (!designTargetIsStructural()) {
      DP.setDesignTarget({ kind: "structural", structural: true, structuralKind, rowId: null, drawerId: null });
    }
    return DP.enter("design", true);
  }
  if (!(await DP.enter("space", true))) return false;
  const ordinary = DL.bins.filter(DL.isOrdinary);
  if (ordinary.length !== 1) return true;
  const row = ordinary[0];
  if (!DP.editableSourceFor(row)) return true;
  try {
    if (!(await DP.openInventoryRow(row.id))) {
      toast("Could not open this bin in Design. The Space is still open.", true, 7000);
    }
  } catch (error) {
    toast(`Could not open this bin in Design: ${error.message}`, true, 7000);
  }
  return true;
};

SP.confirmResume = async () => {
  if (await SP.openTypedSpacePreferredView()) SP.close();
};

// The current folder isn't a typed Space yet (e.g. the user tried to switch
// to the Drawer view). Route it through the same explicit setup flow as
// Open Existing/Configure Existing, using only screens that actually exist -
// the old "Space planning is optional" screen is gone, see Fix 004
// Correction 6.B.
SP.offerSpacePlanning = async () => {
  if (!SP.hasFolder()) return SP.showHome();
  if (!SP.canPersistSpace()) return SP.showFolderAccessNeeded();
  try {
    const folder = state.runtime.hosted ? state.browserFolder : state.output;
    const data = state.runtime.hosted
        ? await SP.inspectHosted(folder)
        : (await api("/api/space/inspect", { output: folder })).folder;
    SP.enterSetupFor(folder, data);
  } catch (error) {
    toast(error.message, true, 6000);
  }
};

// Capability-driven, never an OS or browser name: either this browser cannot
// give writable folder access at all, or access was not granted.
SP.showFolderAccessNeeded = (reason = "unsupported", context = null) => {
  const title = document.querySelector("#space-unsupported .welcome-header h2");
  const lead = document.getElementById("space-unsupported-lead");
  const detail = document.getElementById("space-unsupported-detail");
  // The "Design without a Space" flow must never lecture about Inventory
  // and Spaces: the user explicitly declined a Space. Tell them plainly
  // their work won't be saved to a folder, then let them design.
  if (context === "untyped") {
    if (title) title.textContent = "Designing without a saved folder";
    if (lead) lead.textContent = reason === "denied"
      ? "Wavefinity was not given read/write access to that folder."
      : "This browser cannot give Wavefinity ongoing read/write access to a chosen folder.";
    if (detail) detail.textContent =
      "You can still design and download parts normally — your work just won't be saved into a folder.";
  } else {
    if (title) title.textContent = "Inventory and Spaces need folder access";
    if (reason === "denied") {
      if (lead) lead.textContent =
        "Wavefinity was not given read/write access to that folder.";
      if (detail) detail.textContent =
        "You can still design and download parts normally. Choose the folder again and allow access to use Inventory and Spaces.";
    } else {
      if (lead) lead.textContent =
        "This browser cannot give Wavefinity ongoing read/write access to a chosen folder.";
      if (detail) detail.textContent =
        "You can still design and download parts normally. Inventory and Spaces require a browser that supports writable folder access.";
    }
  }
  SP.showOnly("space-unsupported");
  SP.showDialog();
};

SP.open = () => {
  if (state.folderMode === "space" && state.activeSpace) {
    return SP.showResume({
      folder: state.output,
      folder_name: state.browserFolder?.name || String(state.output).split(/[\\/]/).pop(),
      folder_mode: "space",
      space: state.activeSpace,
    });
  }
  return SP.offerSpacePlanning();
};

// ------------------------------------------------------------ setup


// `message`, when given, is a startup recovery error (Fix 019 Item 6) shown
// in #welcome-startup-error. Ordinary navigation to Welcome (no message)
// clears any previously-shown error.
SP.showHome = (message = null) => {
  SP.showOnly("welcome-home");
  const errorEl = document.getElementById("welcome-startup-error");
  if (errorEl) {
    errorEl.textContent = message || "";
    errorEl.hidden = !message;
  }
  SP.renderRecent();
  // Proactive, not just reactive: on a browser that cannot give writable
  // folder access, the Spaces screen itself says so up front — Spaces and
  // Inventory are unavailable here, but designing still works.
  const folderNotice = document.getElementById("welcome-folder-notice");
  if (folderNotice) {
    folderNotice.hidden = !(state.runtime.hosted && !window.WFFileSystem?.supportsDirectoryPicker());
  }
  const hasRecent = SP.recent.length > 0;
  document.getElementById("welcome-recent-container").hidden = !state.runtime.hosted || !hasRecent;
  SP.renderStorageCard();
  SP.refreshStorage();
  SP.welcomeOtherSpaces();
  SP.showDialog();
};

// The Wavefinity Folder control stays below the main Welcome actions.
SP.renderStorageCard = () => {
  const info = SP.storage;
  document.querySelectorAll("[data-storage-card]").forEach(el => {
    // The card also owns the printer settings, so it stays visible in hosted
    // mode; only the local Wavefinity Folder details come and go.
    const details = el.querySelector("[data-storage-folder-details]");
    const showFolder = !state.runtime.hosted && Boolean(info);
    if (details) details.hidden = !showFolder;
    el.toggleAttribute("data-folder-hidden", !showFolder);
    el.hidden = false;
    if (!showFolder) return;
    const lead = el.querySelector(".welcome-storage-lead");
    if (info.unavailable) {
      lead.textContent = "Your saved Space storage location could not be found. Choose a folder to continue.";
    } else if (!info.explicit) {
      lead.textContent = "Wavefinity folder: Documents (default)";
    } else {
      lead.textContent = "Wavefinity folder";
    }
    const path = el.querySelector(".welcome-storage-path");
    path.textContent = !info.unavailable && info.explicit ? info.root : "";
    path.hidden = !path.textContent;
    const leftover = el.querySelector(".welcome-storage-leftover");
    leftover.hidden = !info.leftover;
    leftover.textContent = info.leftover
      ? `An extra copy of Wavefinity data is still at ${info.leftover}. Wavefinity did not delete it. You can delete it yourself once you are sure you do not need it.`
      : "";
  });
  SP.mountPrinterProfiles?.();
};

// Quietly re-reads the storage state so the card never shows a stale root
// (for example right after the first Space creates the folder).
SP.refreshStorage = async () => {
  if (state.runtime.hosted) return;
  try {
    SP.storage = (await api("/api/space/storage-state", {})).storage || null;
  } catch (_error) {
    return;
  }
  SP.renderStorageCard();
};

// Change Location. With no Wavefinity folder yet (first run, or a missing saved
// location) there is nothing to move, so the chosen parent is simply saved.
// Otherwise the user picks a parent, sees the resulting folder, and chooses
// Move existing data or Use new location; a folder that already exists there
// is never merged or replaced (see SP.renderStoragePlan).
SP.storagePlan = null;
SP.storageReturn = "welcome-home";

SP.changeStorageParent = () => SP.run(SP.startStorageChange);

SP.startStorageChange = async () => {
  SP.storageReturn = $("#welcome-resume").hidden ? "welcome-home" : "welcome-resume";
  await SP.pickStorageParent();
};

SP.pickStorageParent = async () => {
  const picked = await api("/api/space/browse-storage-parent", { pick_only: true });
  if (!picked.folder) return; // a cancel is a no-op
  const data = await api("/api/space/storage-plan", { parent: picked.folder });
  if (data.plan.same) {
    toast("That is already your Wavefinity folder.");
    return;
  }
  SP.storagePlan = data.plan;
  // Nothing to move and nothing at the destination: just use the new location.
  if (!data.plan.source_exists && !data.plan.conflict) {
    await SP.doStorageChange("switch");
    return;
  }
  SP.renderStoragePlan();
};

SP.renderStoragePlan = () => {
  const plan = SP.storagePlan;
  if (!plan) return;
  SP.showOnly("space-storage-change");
  $("#space-storage-choose").hidden = plan.conflict;
  $("#space-storage-conflict").hidden = !plan.conflict;
  $("#space-storage-new-root").textContent = plan.root;
  $("#space-storage-conflict-root").textContent = plan.root;
  const move = document.querySelector('input[name="space-storage-mode"][value="move"]');
  const other = document.querySelector('input[name="space-storage-mode"][value="switch"]');
  move.checked = true;
  other.checked = false;
  SP.showDialog();
};

SP.cancelStorageChange = () => {
  SP.storagePlan = null;
  SP.showOnly(SP.storageReturn);
  SP.renderStorageCard();
  SP.welcomeOtherSpaces();
  SP.showDialog();
};

SP.applyStorageChange = mode => SP.run(() => SP.doStorageChange(mode));

SP.doStorageChange = async mode => {
  const plan = SP.storagePlan;
  if (!plan) return;
  const busyMessage = "Finish the current Space action, then try Change Location again.";
  const writeBusy = includeTimer =>
    (typeof DL !== "undefined" && Boolean(DL.busy || DL.savePromise)) ||
    (typeof designerWriteActive === "function" && designerWriteActive({ includeTimer }));
  // Never relocate underneath a running save/generate/print/refresh.
  if ((typeof DL !== "undefined" && DL.busy) ||
      (typeof designerWriteActive === "function" && designerWriteActive({ includeTimer: false }))) {
    toast(busyMessage, true, 6000);
    return;
  }
  // Settle every write owner (design autosave, inventory, layout); a failed
  // save aborts before anything is changed. No deferred preview may survive.
  if (!(await SP.leaveSpaceSafely({ noDeferredPreview: true }))) return;
  state.relocating = true; // blocks every new write entry point
  document.body.classList.add("relocating");
  if (typeof DL !== "undefined") DL.saveSoon.cancel();
  let reloading = false;
  try {
    if (typeof settleDesignerWritesForRelocation === "function") await settleDesignerWritesForRelocation();
    await SP.flushOutgoingResumeCheckpoint();
    await SP.flushDefaults();
    if (writeBusy(true) || (typeof DL !== "undefined" && DL.dirty)) {
      toast(busyMessage, true, 6000);
      return;
    }
    const data = await api("/api/space/storage-change", { parent: plan.parent, mode });
    if (data.status === "conflict") {
      SP.storagePlan = { ...plan, conflict: true };
      SP.renderStoragePlan();
      return;
    }
    SP.storagePlan = null;
    SP.storage = data.storage || null;
    if (data.status === "unchanged") {
      toast("That is already your Wavefinity folder.");
      SP.cancelStorageChange();
      return;
    }
    // Reload at once so no owner can write to the old path; the card shows any
    // leftover old copy after the reload.
    reloading = true;
    location.reload();
  } finally {
    if (!reloading) {
      state.relocating = false;
      document.body.classList.remove("relocating");
      if (typeof DL !== "undefined" && DL.dirty) DL.saveSoon();
    }
  }
};

SP.showTypeCards = () => {
  SP.destroyStorageDrawersForm?.();
  // An arbitrary existing folder can never be converted into a Storage Drawers
  // Space: the card is not offered while a folder is being given a type.
  const arbitrary = Boolean(SP.configureData);
  document.querySelectorAll('.type-card[data-kind="storage_drawers"]').forEach(card => { card.hidden = arbitrary; });
  SP.showOnly("space-type-cards");
  SP.showDialog();
  SP.dialog().scrollTop = 0;
};

SP.showTutorial = () => {
  SP.showOnly("space-tutorial");
  SP.showDialog();
  SP.dialog().scrollTop = 0;
};

