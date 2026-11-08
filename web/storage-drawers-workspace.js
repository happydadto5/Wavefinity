/* Cabinet navigator and structural actions; mounted by the Space host in 084B. */
(() => {
  "use strict";
  const el = (tag, className, text) => { const node = document.createElement(tag); node.className = className; node.textContent = text; return node; };
  const drawerText = (row, index, bins, fitMm = 0) => {
    const parts = [`Drawer ${index + 1}`];
    const label = (row.label_text || "").trim();
    if (label) parts.push(label);
    parts.push(`${fmt(Math.round((row.height_mm + fitMm) * 1000) / 1000)} mm`);
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
    const selectors = () => Array.from(list.querySelectorAll(".sd-drawer-select"));
    const render = () => {
      const damaged = Boolean(current.recovery);
      recovery.hidden = !damaged; panel.hidden = damaged;
      if (damaged) {
        recoveryMessage.textContent = current.recovery.message || "A cabinet setting is not valid.";
        list.replaceChildren();
        return;
      }
      const space = current.space, layout = current.layout;
      const rows = window.StorageDrawers.drawerDescriptors(space);
      const maxHeight = Math.max(...rows.map(row => row.height_mm));
      // Fix 1109: capture which drawer selector holds keyboard focus before
      // the list is rebuilt, so focus can be restored to the same drawer.
      const focusedDrawerId = list.contains(document.activeElement)
        ? document.activeElement?.dataset?.drawerId || null
        : null;
      list.replaceChildren();
      rows.forEach((row, index) => {
        const item = el("div", "sd-drawer-item", "");
        const placed = layout.drawers?.find(one => one.id === row.id)?.placements?.length || 0;
        const selector = el("button", "sd-drawer-select", drawerText(row, index, placed, space.storage_drawers.drawer_fit_mm));
        // Fix 1107 (Astra AD-006): visible drawer-switch lock. The flag is
        // Fix 1108's `current.structuralBusy`, read inline — no parallel state.
        // (Fix 1108's own `const structuralBusy` is declared later in render(),
        // so it cannot be reused here. The title phrases from 1108's
        // operation-specific `current.structuralBusyLabel` — round 2, G2M-0429.)
        selector.type = "button"; selector.disabled = editing || Boolean(current.structuralBusy);
        if (current.structuralBusy) selector.title = `${current.structuralBusyLabel || "Working"} — drawer switching is locked until it finishes.`;
        else if (editing) selector.title = "Finish editing the current drawer first.";
        selector.dataset.drawerId = row.id;
        selector.setAttribute("aria-pressed", String(layout.active === row.id));
        // Fix 1109: the accessible name carries the same identifying details
        // as the visible text (custom label, usable height, bin count).
        selector.setAttribute("aria-label", drawerText(row, index, placed, space.storage_drawers.drawer_fit_mm));
        selector.dataset.size = String(Math.max(0, Math.min(4, Math.round(row.height_mm / maxHeight * 4))));
        selector.addEventListener("click", async () => {
          if (editing || layout.active === row.id) return;
          const oldId = layout.active;
          await callbacks.setActiveDrawer?.(row.id);
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
        item.append(selector); list.append(item);
      });
      // Fix 1109: restore keyboard focus to the same drawer after the rebuild.
      // Selection and layout/report updates all funnel through render(), so
      // this covers every path that destroys the focused button. Pointer
      // users are untouched: restore only fires when focus was inside the list.
      if (focusedDrawerId) {
        const focusedSelector = selectors().find(button => button.dataset.drawerId === focusedDrawerId);
        if (focusedSelector && !focusedSelector.disabled) focusedSelector.focus({ preventScroll: true });
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
