/* Cabinet navigator and structural actions; mounted by the Space host in 084B. */
(() => {
  "use strict";
  const el = (tag, className, text) => { const node = document.createElement(tag); node.className = className; node.textContent = text; return node; };
  const mount = ({ host, state, callbacks = {} }) => {
    let current = state, editing = !!state?.editing;
    host.replaceChildren();
    const panel = el("section", "sd-navigator", ""); panel.setAttribute("aria-label", "Cabinet drawers");
    const title = el("h3", "", "Storage Drawers"); const list = el("div", "sd-navigator-list", "");
    panel.append(title, list);
    const add = el("button", "button", "Add Drawer"); add.type = "button";
    add.addEventListener("click", () => { if (!editing) callbacks.addDrawer?.(); }); panel.append(add);
    const structural = el("section", "sd-structural", "");
    const status = el("p", "sd-structural-status", "Cabinet files need save");
    const fit = el("p", "sd-printer-fit", "");
    const save = el("button", "button", "Save Cabinet"), print = el("button", "button", "Print Cabinet");
    save.type = print.type = "button";
    save.addEventListener("click", () => callbacks.saveCabinet?.());
    print.addEventListener("click", () => callbacks.printCabinet?.());
    structural.append(status, fit, save, print); host.append(panel, structural);
    const selectors = () => Array.from(list.querySelectorAll(".sd-drawer-select"));
    const render = () => {
      const space = current.space, layout = current.layout;
      const rows = window.StorageDrawers.drawerDescriptors(space);
      const maxHeight = Math.max(...rows.map(row => row.height_mm));
      list.replaceChildren();
      rows.forEach((row, index) => {
        const item = el("div", "sd-drawer-item", "");
        const selector = el("button", "sd-drawer-select", `Drawer ${index + 1} · ${row.height_mm} mm`);
        selector.type = "button"; selector.disabled = editing;
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
        const remove = el("button", "sd-drawer-delete", "Delete"); remove.type = "button";
        remove.disabled = editing || rows.length <= 1; remove.setAttribute("aria-label", `Delete Drawer ${index + 1}`);
        remove.addEventListener("click", () => { if (!editing) callbacks.deleteDrawer?.(row.id); });
        item.append(selector, remove); list.append(item);
      });
      add.disabled = editing || rows.length >= 32;
      status.textContent = ({ saved: "Cabinet files saved", need_update: "Cabinet files need update", need_save: "Cabinet files need save" })[current.structuralStatus?.status || current.structuralStatus] || "Cabinet files need save";
      fit.textContent = current.summary?.fits_printer ? "Fits printer" : current.summary?.first_fit_error || "";
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
