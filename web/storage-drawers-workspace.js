/* Cabinet navigator and structural actions; mounted by the Space host in 084B. */
(() => {
  "use strict";
  const GUIDE_URL = "/storage-drawers-guide.html";
  const el = (tag, className, text) => { const node = document.createElement(tag); node.className = className; node.textContent = text; return node; };
  const drawerText = (row, index, bins) => {
    const parts = [`Drawer ${index + 1}`];
    const label = (row.label_text || "").trim();
    if (label) parts.push(label);
    parts.push(`${fmt(row.height_mm)} mm`);
    if (bins > 0) parts.push(`${bins} ${bins === 1 ? "bin" : "bins"}`);
    return parts.join(" · ");
  };
  const mount = ({ host, state, callbacks = {} }) => {
    let current = state, editing = !!state?.editing;
    host.replaceChildren();
    const panel = el("section", "sd-navigator", ""); panel.setAttribute("aria-label", "Cabinet drawers");
    const title = el("h3", "", "Storage Drawers"); const list = el("div", "sd-navigator-list", "");
    // Fix 096 F9: visible reason when drawer controls are disabled while editing.
    const editNote = el("small", "sd-help", ""); editNote.id = "sd-edit-note"; editNote.hidden = true;
    panel.append(title, editNote, list);
    const add = el("button", "button", "Add Drawer"); add.type = "button";
    add.addEventListener("click", () => { if (!editing) callbacks.addDrawer?.(); });
    const addNote = el("small", "sd-help", ""); addNote.id = "sd-add-note"; addNote.hidden = true;
    add.setAttribute("aria-describedby", addNote.id);
    panel.append(add, addNote);
    const structural = el("section", "sd-structural", "");
    const status = el("p", "sd-structural-status", "Cabinet files need save");
    const fit = el("p", "sd-printer-fit", "");
    const printerRow = el("p", "sd-printer-row-note", "");
    const printerButton = el("button", "link-button", "Printer Settings…"); printerButton.type = "button";
    printerButton.addEventListener("click", () => callbacks.openPrinterSettings?.());
    const save = el("button", "button sd-save", "Save Cabinet"), print = el("button", "button sd-print", "Print Cabinet");
    const printBoth = el("button", "button sd-print-both", "Print Cabinet + Bins");
    save.type = print.type = printBoth.type = "button";
    save.addEventListener("click", () => callbacks.saveCabinet?.());
    print.addEventListener("click", event => callbacks.printCabinet?.(event));
    printBoth.addEventListener("click", event => callbacks.printCabinetAndBins?.(event));
    const guide = el("a", "sd-guide-link", "Assembly & print guide"); guide.href = GUIDE_URL; guide.target = "_blank"; guide.rel = "noopener";
    structural.append(status, fit, printerRow, save, print, printBoth, guide);
    // Damaged known cabinet settings: Inventory and designs stay usable, cabinet
    // output stays off, and one button repairs only the cabinet definition.
    const recovery = el("section", "sd-recovery", ""); recovery.hidden = true;
    const recoveryTitle = el("h3", "", "Cabinet settings need repair");
    const recoveryMessage = el("p", "sd-recovery-message", "");
    const recoveryNote = el("p", "sd-help", "Your Inventory and bin designs are untouched. Resetting keeps every drawer that is still valid and replaces only what is damaged with current defaults.");
    const reset = el("button", "button primary", "Reset Cabinet Settings"); reset.type = "button";
    reset.addEventListener("click", () => callbacks.resetCabinet?.());
    recovery.append(recoveryTitle, recoveryMessage, recoveryNote, reset);
    host.append(panel, structural, recovery);
    const selectors = () => Array.from(list.querySelectorAll(".sd-drawer-select"));
    const render = () => {
      const damaged = Boolean(current.recovery);
      recovery.hidden = !damaged; panel.hidden = damaged; structural.hidden = damaged;
      printerRow.replaceChildren(`Printer: ${current.printer ? `${fmt(current.printer.x_mm)} × ${fmt(current.printer.y_mm)} × ${fmt(current.printer.z_mm)} mm` : "—"} `, printerButton);
      if (damaged) {
        recoveryMessage.textContent = current.recovery.message || "A cabinet setting is not valid.";
        list.replaceChildren();
        return;
      }
      const space = current.space, layout = current.layout;
      const maxDrawers = window.StorageDrawers.rules().maxDrawers;
      const rows = window.StorageDrawers.drawerDescriptors(space);
      const maxHeight = Math.max(...rows.map(row => row.height_mm));
      list.replaceChildren();
      rows.forEach((row, index) => {
        const item = el("div", "sd-drawer-item", "");
        const placed = layout.drawers?.find(one => one.id === row.id)?.placements?.length || 0;
        const selector = el("button", "sd-drawer-select", drawerText(row, index, placed));
        selector.type = "button"; selector.disabled = editing;
        if (editing) selector.title = "Finish editing the current drawer first.";
        selector.setAttribute("aria-pressed", String(layout.active === row.id));
        selector.setAttribute("aria-label", `Select Drawer ${index + 1}`);
        selector.dataset.size = String(Math.max(0, Math.min(4, Math.round(row.height_mm / maxHeight * 4))));
        selector.addEventListener("click", async () => {
          if (editing || layout.active === row.id) return;
          const oldId = layout.active;
          await callbacks.setActiveDrawer?.(row.id, { history: false });
          callbacks.clearCanvasPlacementSelection?.();
          const selectedRow = callbacks.selectedRow?.();
          if (selectedRow && window.StorageDrawers.drawerHoldingRow(layout, selectedRow) === oldId) callbacks.clearSelectedRow?.();
          callbacks.reframeCamera?.();
        });
        selector.addEventListener("keydown", event => {
          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
          event.preventDefault();
          selectors()[Math.max(0, Math.min(rows.length - 1, index + (event.key === "ArrowUp" ? -1 : 1)))]?.focus();
        });
        const remove = el("button", "button danger sd-drawer-delete", "Delete"); remove.type = "button";
        remove.disabled = editing || rows.length <= 1; remove.setAttribute("aria-label", `Delete Drawer ${index + 1}`);
        if (rows.length <= 1) remove.title = "Keep at least one drawer";
        if (editing) remove.title = "Finish editing the current drawer first.";
        // Fix 096 F9: visible reason for the single-drawer Delete disable.
        const singleNote = el("small", "sd-help", "");
        singleNote.hidden = rows.length > 1;
        singleNote.textContent = rows.length > 1 ? "" : "Keep at least one drawer.";
        remove.addEventListener("click", () => { if (!editing) callbacks.deleteDrawer?.(row.id); });
        item.append(selector, remove, singleNote); list.append(item);
      });
      const atMax = rows.length >= maxDrawers;
      add.disabled = editing || atMax;
      add.title = atMax ? `Maximum ${maxDrawers} drawers` : editing ? "Finish editing the current drawer first." : "";
      addNote.hidden = !atMax; addNote.textContent = atMax ? `Maximum ${maxDrawers} drawers` : "";
      // Fix 096 F9: one visible reason covering every drawer control disabled while editing.
      editNote.hidden = !editing;
      editNote.textContent = editing ? "Finish editing the current drawer to switch, add, or delete drawers." : "";
      const code = current.structuralStatus?.status || current.structuralStatus;
      status.textContent = code === "recovery_error" && current.structuralStatus.message
        ? current.structuralStatus.message
        : ({ saved: "Cabinet files saved", need_update: "Cabinet files need update", need_save: "Cabinet files need save" })[code] || "Cabinet files need save";
      fit.textContent = current.summary?.fits_printer ? "Fits printer" : current.summary?.first_fit_error || "";
      fit.classList.toggle("bad", Boolean(current.summary) && !current.summary.fits_printer);
    };
    render();
    return {
      update(next) { current = next; editing = !!next.editing; render(); },
      rowLocationText(rowId) { return window.StorageDrawers.rowLocationText(current.layout, rowId); },
      async jumpToInventoryRow(rowId) {
        const drawerId = window.StorageDrawers.drawerHoldingRow(current.layout, rowId);
        if (!drawerId) return false;
        await callbacks.setActiveDrawer?.(drawerId, { history: false, preserveSelectedRow: rowId });
        callbacks.selectRow?.(rowId); callbacks.revealPlacement?.(rowId); callbacks.reframeCamera?.();
        return true;
      },
      destroy() { host.replaceChildren(); }
    };
  };
  window.StorageDrawersWorkspace = { mount };
})();
