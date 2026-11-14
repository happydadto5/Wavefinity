"use strict";

// ---- folder printer build volume (one runtime authority: PrinterProfile)

SP.validFolderPrinter = raw => {
  try { return raw ? PrinterProfile.normalise(raw) : null; }
  catch (_) { return null; }
};

SP.adoptFolderPrinter = raw => {
  state.folderPrinterProfile = SP.validFolderPrinter(raw);
  SP.printerSetupActive = false;
  PrinterProfile.loadLocal(state.folderPrinterProfile
    ? { profile: state.folderPrinterProfile, explicit: true }
    : (SP.globalPrinterProfile || { profile: PrinterProfile.DEFAULT, explicit: false }));
};

SP.isNewSpacePrinterDraft = () =>
  Boolean(SP.printerSetupActive && (WS.task === "newspace" || (SP.dialog().open && !SP.isUpdate)));

SP.syncSetupPrinterCaps = profile => {
  const active = profile || PrinterProfile.DEFAULT;
  SP.setupPrinterProfile = active;
  SP.storageDrawersForm?.setPrinterProfile(active);
  if (SP.setupKind === "portable") {
    for (const axis of ["x", "y", "z"]) document.getElementById(`portable-${axis}`).max = active[`${axis}_mm`];
    SP.refreshSetupError();
    SP.refreshSetupOutside?.();
  }
};

SP.saveFolderPrinter = async (profile, { reset = false } = {}) => {
  if (SP.isNewSpacePrinterDraft()) {
    const next = reset ? null : PrinterProfile.normalise(profile);
    SP.syncSetupPrinterCaps(next || { ...PrinterProfile.DEFAULT });
    return { profile: SP.setupPrinterProfile, explicit: Boolean(next) };
  }
  const requireOwner = SP.spaceOwnerGuard();
  if (!state.activeSpaceId) {
    const saved = await api("/api/space/printer-profile", reset ? { reset: true } : { profile });
    SP.globalPrinterProfile = saved;
    requireOwner();
    return saved;
  }
  const next = reset ? null : PrinterProfile.normalise(profile);
  if (state.runtime.hosted) {
    await SP.writeMetadata(state.browserFolder.handle, "space", null, true,
      { printer_profile: next }, { preserveSpace: true, expectedSpaceId: state.activeSpaceId });
  } else {
    await api("/api/space/printer-profile", { output: state.output, space_id: state.activeSpaceId,
      ...(reset ? { reset: true } : { profile: next }) });
  }
  requireOwner();
  state.folderPrinterProfile = next;
  if (SP.isUpdate) SP.syncSetupPrinterCaps(next);
  return { profile: next || PrinterProfile.DEFAULT, explicit: Boolean(next) };
};

// A draft is kept separate from the outgoing folder's live PrinterProfile.
SP.askPrinterBed = (initial = null) => new Promise(resolve => {
  const dialog = document.createElement("dialog");
  dialog.className = "welcome-dialog printer-settings-dialog";
  dialog.setAttribute("aria-labelledby", "folder-printer-bed-title");
  const form = document.createElement("form");
  const title = document.createElement("h2");
  title.id = "folder-printer-bed-title";
  title.textContent = "Printer bed size for this folder";
  const lead = document.createElement("p");
  lead.textContent = "Enter the printer's bed width, bed depth and build height in millimetres before configuring this folder.";
  form.append(title, lead);
  const inputs = {};
  for (const [axis, name] of [["x", "Bed width"], ["y", "Bed depth"], ["z", "Build height"]]) {
    const label = document.createElement("label");
    label.className = "space-field";
    label.append(`${name} (mm)`);
    const input = document.createElement("input");
    input.type = "number"; input.min = "10"; input.max = "1000"; input.step = "any"; input.required = true;
    input.value = initial?.[`${axis}_mm`] ?? "";
    label.append(input); form.append(label); inputs[axis] = input;
  }
  const error = document.createElement("p");
  error.className = "field-error"; error.setAttribute("role", "alert");
  const actions = document.createElement("div");
  actions.className = "welcome-actions";
  const cancel = document.createElement("button");
  cancel.type = "button"; cancel.className = "button secondary"; cancel.textContent = "Cancel";
  const save = document.createElement("button");
  save.type = "submit"; save.className = "button primary"; save.textContent = "Continue";
  actions.append(cancel, save); form.append(error, actions); dialog.append(form);
  let result = null;
  cancel.addEventListener("click", () => dialog.close());
  form.addEventListener("submit", event => {
    event.preventDefault();
    try {
      result = PrinterProfile.normalise(Object.fromEntries(["x", "y", "z"].map(axis => [`${axis}_mm`, Number(inputs[axis].value)])));
      dialog.close();
    } catch (failure) { error.textContent = failure.message; }
  });
  dialog.addEventListener("close", () => { dialog.remove(); resolve(result); }, { once: true });
  document.body.append(dialog); dialog.showModal(); inputs.x.focus();
});

SP.ensureSetupPrinterProfile = async ({ update = false } = {}) => {
  if (SP.setupPrinterProfile) return true;
  // Multiple navigation callbacks must share the same first-step prompt.
  if (SP.printerSetupPending) return SP.printerSetupPending;
  SP.printerSetupPending = (async () => {
    const requireOwner = SP.spaceOwnerGuard();
    const profile = await SP.askPrinterBed();
    if (!profile) return false;
    requireOwner();
    if (update) {
      try {
        const saved = await SP.saveFolderPrinter(profile);
        PrinterProfile.loadLocal(saved);
      } catch (error) { toast(`Printer bed size could not be saved: ${error.message}`, true, 6000); return false; }
    }
    SP.setupPrinterProfile = profile;
    SP.printerSetupActive = !update;
    return true;
  })();
  try { return await SP.printerSetupPending; }
  catch (error) { toast(error.message, true, 6000); return false; }
  finally { SP.printerSetupPending = null; }
};

SP._printerHosts = new Map();

SP.mountPrinterProfiles = () => {
  document.querySelectorAll("[data-printer-profile-host]").forEach(host => {
    if (SP._printerHosts.has(host)) return;
    const callbacks = {
      write: async (_key, value) => {
        const saved = await SP.saveFolderPrinter(value.profile);
        PrinterProfile.loadLocal(saved);
      },
      // Only the printer keys return to defaults, and the reset is persisted.
      reset: async () => {
        const saved = await SP.saveFolderPrinter(null, { reset: true });
        PrinterProfile.loadLocal(saved);
      },
      onError: error => toast(error.message, true, 6000),
    };
    SP._printerHosts.set(host, PrinterProfile.mount(host, callbacks));
  });
};

SP.initPrinterProfile = async () => {
  try {
    const local = await api("/api/space/printer-profile", {});
    PrinterProfile.loadLocal(local);
    if (local.explicit) PrinterProfile.retireLegacyBaseTrim();
    if (!local.explicit && !local.malformed) {
      const seed = PrinterProfile.readLegacyBaseTrimSeed();
      // The old Base Trim key is retired only after the new authority holds it.
      if (seed) {
        const saved = await api("/api/space/printer-profile", { profile: { ...seed } });
        PrinterProfile.loadLocal(saved);
        PrinterProfile.retireLegacyBaseTrim();
      }
    }
  } catch (error) {
    toast(`Printer settings could not be loaded: ${error.message}`, true, 6000);
  }
  SP.globalPrinterProfile = { profile: PrinterProfile.current(), explicit: PrinterProfile.configured(),
    malformed: PrinterProfile.malformedMessage() };
  PrinterProfile.subscribe(profile => {
    SP.storageDrawersForm?.setPrinterProfile(profile);
    SP.cabinetInfo.key = "";
    SP.updateCabinetWorkspace();
    SP.invalidateBaseTrimSummary();
  });
  SP.mountPrinterProfiles();
};

// ---- Printer Settings dialog: the one PrinterProfile authority, reachable from
// the setup Summary and from the cabinet panel. Closing it changes nothing else.

SP.openPrinterSettings = async () => {
  SP.renderSettingsHomeFolder?.();
  const dialog = document.getElementById("printer-settings-dialog");
  if (!dialog || dialog.open) return;
  if (SP.isNewSpacePrinterDraft() && SP.setupPrinterProfile) {
    const previous = { profile: PrinterProfile.current(), explicit: PrinterProfile.configured() };
    PrinterProfile.loadLocal({ profile: SP.setupPrinterProfile, explicit: true });
    dialog.addEventListener("close", () => {
      if (SP.isNewSpacePrinterDraft()) PrinterProfile.loadLocal(previous);
    }, { once: true });
  }
  dialog.showModal();
};

SP.closePrinterSettings = () => {
  const dialog = document.getElementById("printer-settings-dialog");
  if (dialog?.open) dialog.close();
};

// ---- Header Settings opens Settings directly; folder, printer bed and slicer live in that dialog.
document.getElementById("designer-settings-open")?.addEventListener("click", () => SP.openPrinterSettings());
document.getElementById("settings-home-folder-change")?.addEventListener("click", () => SP.changeSettingsHomeFolder?.());
document.getElementById("settings-slicer-picker")?.addEventListener("click", event => {
  browseSlicer(event.currentTarget);
});

