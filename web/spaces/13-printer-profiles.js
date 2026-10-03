"use strict";

// ---- global printer build volume (one runtime authority: PrinterProfile)

SP._printerHosts = new Map();

SP.mountPrinterProfiles = () => {
  document.querySelectorAll("[data-printer-profile-host]").forEach(host => {
    if (SP._printerHosts.has(host)) return;
    const callbacks = state.runtime.hosted
      ? { hosted: true, reset: () => PrinterProfile.resetHosted(), onError: error => toast(error.message, true, 6000) }
      : {
        write: async (_key, value) => {
          const saved = await api("/api/space/printer-profile", { profile: value.profile });
          PrinterProfile.loadLocal(saved);
        },
        // Only the printer keys return to defaults, and the reset is persisted.
        reset: async () => {
          const saved = await api("/api/space/printer-profile", { reset: true });
          PrinterProfile.loadLocal(saved);
        },
        onError: error => toast(error.message, true, 6000),
      };
    SP._printerHosts.set(host, PrinterProfile.mount(host, callbacks));
  });
};

SP.initPrinterProfile = async () => {
  try {
    if (state.runtime.hosted) {
      const loaded = await PrinterProfile.loadHosted();
      if (!loaded.explicit && !loaded.malformed) {
        PrinterProfile.persistHosted(PrinterProfile.readLegacyBaseTrimSeed() || PrinterProfile.DEFAULT);
      }
      PrinterProfile.retireLegacyBaseTrim();
    } else {
      const local = await api("/api/space/printer-profile", {});
      PrinterProfile.loadLocal(local);
      if (!local.explicit && !local.malformed) {
        const seed = PrinterProfile.readLegacyBaseTrimSeed() || PrinterProfile.DEFAULT;
        // The old Base Trim key is retired only after the new authority holds it.
        const saved = await api("/api/space/printer-profile", { profile: { ...seed } });
        PrinterProfile.loadLocal(saved);
        PrinterProfile.retireLegacyBaseTrim();
      }
    }
  } catch (error) {
    toast(`Printer settings could not be loaded: ${error.message}`, true, 6000);
  }
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

SP.openPrinterSettings = () => {
  const dialog = document.getElementById("printer-settings-dialog");
  if (dialog && !dialog.open) dialog.showModal();
};

SP.closePrinterSettings = () => {
  const dialog = document.getElementById("printer-settings-dialog");
  if (dialog?.open) dialog.close();
};

