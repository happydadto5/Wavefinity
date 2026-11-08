/* Cabinet navigator and structural actions; mounted by the Space host in 084B. */
(() => {
  "use strict";
  const el = (tag, className, text) => { const node = document.createElement(tag); node.className = className; node.textContent = text; return node; };
  const mount = ({ host, state, callbacks = {} }) => {
    let current = state, editing = !!state?.editing;
    host.replaceChildren();
    const panel = el("section", "sd-navigator", ""); panel.setAttribute("aria-label", "Cabinet drawers");
    // Drawer switching lives in the "Layout your space" row (Story 2752); this panel only carries notes.
    // Fix 096 F9: visible reason when drawer controls are disabled while editing.
    const editNote = el("small", "sd-help", ""); editNote.id = "sd-edit-note"; editNote.hidden = true;
    panel.append(editNote);
    // The floating cabinet card is gone (Story 2748): Save/Print/Printer/guide
    // live in the left controls. Only the placement-lock note stays, here.
    const busyNote = el("p", "sd-help", "");
    busyNote.hidden = true;
    panel.append(busyNote);
    // Damaged known cabinet settings: Inventory and designs stay usable, cabinet
    // output stays off, and one button repairs only the cabinet definition.
    const recovery = el("section", "sd-recovery", ""); recovery.hidden = true;
    const recoveryTitle = el("h3", "", "Cabinet settings need repair");
    const recoveryMessage = el("p", "sd-recovery-message", "");
    const recoveryNote = el("p", "sd-help", "Your Inventory and bin designs are untouched. Resetting keeps every drawer that is still valid and replaces only what is damaged with current defaults.");
    const reset = el("button", "button primary", "Reset Cabinet Settings"); reset.type = "button";
    reset.addEventListener("click", () => callbacks.resetCabinet?.());
    recovery.append(recoveryTitle, recoveryMessage, recoveryNote, reset);
    host.append(panel, recovery);
    const render = () => {
      const damaged = Boolean(current.recovery);
      recovery.hidden = !damaged; panel.hidden = damaged || (!editing && !current.structuralBusy);
      if (damaged) {
        recoveryMessage.textContent = current.recovery.message || "A cabinet setting is not valid.";
        return;
      }
      // Add/Delete Drawer live in Design only; the navigator just switches drawers.
      editNote.hidden = !editing;
      editNote.textContent = editing ? "Finish editing the current drawer to switch drawers." : "";
      // Fix 1107 (Astra AD-006): explicit placement-lock note. The busy flag,
      // the Save/Print disabling, and the operation-specific pending label are
      // owned by Fix 1108 — this contract only toggles the note and phrases
      // its copy from 1108's structuralBusyLabel, so Save Cabinet never claims
      // to be "Printing".
      // (round 2, GPT G2M-0429: hard-coded "Printing — …" copy was false when
      // Save Cabinet or cabinet-only Print holds the busy flag.)
      if (current.structuralBusy) {
        busyNote.textContent = `${current.structuralBusyLabel || "Working"} — placement is locked until it finishes.`;
        busyNote.hidden = false;
      } else {
        busyNote.hidden = true;
      }
    };
    render();
    return {
      update(next) { current = next; editing = !!next.editing; render(); },
      rowLocationText(rowId) { return window.StorageDrawers.rowLocationText(current.layout, rowId); },
      async jumpToInventoryRow(rowId) {
        const drawerId = window.StorageDrawers.drawerHoldingRow(current.layout, rowId);
        if (!drawerId) return false;
        await callbacks.setActiveDrawer?.(drawerId, { preserveSelectedRow: rowId });
        callbacks.selectRow?.(rowId); callbacks.revealPlacement?.(rowId); callbacks.reframeCamera?.();
        return true;
      },
      destroy() { host.replaceChildren(); }
    };
  };
  window.StorageDrawersWorkspace = { mount };
})();
