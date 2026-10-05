/* Create/Edit cabinet draft. No route or persistence calls live here. */
(() => {
  "use strict";
  let mountSerial = 0;
  const GUIDE_URL = "/storage-drawers-guide.html";
  const copy = value => structuredClone(value);
  const el = (tag, className = "", text = "") => {
    const node = document.createElement(tag); node.className = className; node.textContent = text; return node;
  };
  const help = text => el("small", "sd-help", text);
  const labeled = (title, input, helper = null, unit = "") => {
    const label = el("label", "sd-field", title);
    if (unit) label.append(" ", el("span", "unit", unit));
    label.append(input);
    if (helper) label.append(help(helper));
    return label;
  };
  const input = (value, type = "text") => { const node = document.createElement("input"); node.type = type; node.value = value ?? ""; return node; };
  const select = (value, choices) => {
    const node = document.createElement("select");
    for (const [key, title] of choices) { const option = document.createElement("option"); option.value = key; option.textContent = title; node.append(option); }
    node.value = String(value); return node;
  };
  const group = (host, title) => { const section = el("div", "sd-form-group storage-box-group"); section.append(el("h5", "storage-box-subtitle", title)); host.append(section); return section; };
  const materialChoices = (catalog, kind, current) => {
    const rows = catalog?.b4b_rules?.[kind] || [];
    const options = rows.map(row => {
      const [value, label] = Array.isArray(row)
        ? [String(row[0]), String(row[1])]
        : [String(row.value ?? row.mm), String(row.label ?? row.name)];
      return [value, /\bmm\b/i.test(label) ? label : `${label} — ${value} mm`];
    });
    if (!options.some(row => Number(row[0]) === Number(current))) options.push([String(current), `${current} mm — Current setting`]);
    return options;
  };
  const NAMED = (list, names, unit = "mm") => list.map((mm, index) => [String(mm),
    list.length === names.length ? `${names[index]} · ${mm.toFixed(2).replace(/\.?0+$/, "")} ${unit}` : `${mm} ${unit}`]);
  const mount = ({ host, initialSpace, catalog, printerProfile, mode, callbacks = {}, onReadyChange = null, scope = "full" }) => {
    const epoch = ++mountSerial;
    const rules = window.StorageDrawers.catalogRules(catalog);
    const { baseUnit, minDrawerHeight, minUnits, maxUnits, minDrawers, maxDrawers, labelLimit } = rules;
    const defaults = () => ({
      drawers: Array.from({ length: 3 }, () => ({ temp_key: `temporary:${crypto.randomUUID()}`, height_mm: rules.defaultHeight - rules.defaultFit, label_text: "" })),
      cabinet_style: "full", rear_support: "cross", open_frame_width_mm: rules.defaultFrame, drawer_fit_mm: rules.defaultFit,
      wall_mounting: "off", wall_mount_keyholes_per_drawer: 2,
      drawer_handles: true, drawer_handle_size: "auto", stacking: false,
      unit_label_enabled: false, unit_label_text: "", drawer_labels_enabled: false, drawer_label_style: "inlaid",
      cabinet_wall_mm: 1.6, cabinet_base_mm: 1.6, cabinet_top_mm: 1.6, drawer_wall_mm: 1.6, drawer_base_mm: 1.6,
    });
    let live = true, timer = null, requestNumber = 0, profileEpoch = 0;
    const events = new AbortController();
    let summaryState = "pending", summaryError = "", summaryKey = null, summaryIdentity = null, disabled = false, lastSummary = null, lastReady = null;
    // Waiters for the in-flight live validation (Create/Save clicked while
    // the cabinet check is pending): resolved when the check settles.
    let settleWaiters = [];
    const markSettled = () => {
      if (!settleWaiters.length) return;
      const waiters = settleWaiters; settleWaiters = [];
      for (const done of waiters) { try { done(); } catch { /* a waiter must never break validation */ } }
    };
    // A brand-new Space starts at the legal grid size nearest 210 × 120 mm; a
    // supplied prefill keeps its own dimensions exactly.
    const startMm = mm => baseUnit * Math.min(maxUnits, Math.max(minUnits, Math.round(mm / baseUnit)));
    const space = copy(initialSpace || { kind: "storage_drawers", name: "", x: startMm(210), y: startMm(120) });
    space.storage_drawers = { ...defaults(), ...copy(space.storage_drawers || {}) };
    const block = space.storage_drawers;
    const tail = [];
    host.replaceChildren();
    // Basic scope (New Space and header Edit) is the compact layout: Basics +
    // Drawers + a quiet status line. Full scope (Design) adds Cabinet and Finish.
    const compact = scope === "basic";
    const form = el("div", compact ? "sd-form sd-form-compact" : "sd-form"); host.append(form);
    const name = input(space.name); name.maxLength = 80; name.required = true;
    name.id = `sd-name-${epoch}`;
    name.dataset.heightNeutral = "1";
    const sizeGroup = group(form, "Basics"); sizeGroup.classList.add("sd-basics-group");
    sizeGroup.append(labeled("Space name", name));
    const sizeGrid = el("div", "sd-size-grid"); sizeGroup.append(sizeGrid);
    const x = input(space.x), y = input(space.y);
    x.id = `sd-x-${epoch}`; y.id = `sd-y-${epoch}`;
    const resolveMm = field => {
      const raw = field.value.trim();
      const requested = Number(raw);
      if (!raw || !Number.isFinite(requested) || requested <= 0) return { ok: false };
      const units = Math.round(requested / baseUnit);
      if (units < minUnits || units > maxUnits) return { ok: false };
      return { ok: true, units, mm: units * baseUnit };
    };
    const sizeHelp = new Map([[x, help("")], [y, help("")]]);
    const formatMm = field => {
      const resolved = resolveMm(field);
      sizeHelp.get(field).textContent = resolved.ok
        ? (Number(field.value) === resolved.mm
          ? `${baseUnit} mm grid`
          : `Will save as ${resolved.mm} mm · ${baseUnit} mm grid`)
        : `${baseUnit} mm grid · valid range ${minUnits * baseUnit}–${maxUnits * baseUnit} mm`;
    };
    for (const field of [x, y]) { field.inputMode = "decimal"; field.required = true; }
    // Usable height is local: the stored clear height plus the selected fit.
    const structural = scope === "full" && callbacks.structural === true;
    const zField = input("", "number"); zField.id = `sd-z-${epoch}`; zField.step = "any";
    zField.dataset.usableHeight = "1";
    const zHelp = help("");
    const zLabel = labeled("Usable height", zField, null, "mm"); zLabel.append(zHelp);
    for (const [field, title] of [[x, structural ? "Interior Width" : "Width"], [y, structural ? "Interior Depth" : "Depth"]]) {
      const label = labeled(title, field, null, "mm"); label.append(sizeHelp.get(field)); sizeGrid.append(label);
    }
    if (structural) { sizeGrid.classList.add("sd-size-grid-three"); sizeGrid.append(zLabel); }
    // Fix 103 (Packet B): printer status lives beside Size, not in Summary.
    // Known oversize shows a warning here but does not block.
    const printerRow = el("p", "sd-printer-row");
    sizeGroup.append(printerRow);
    const updatePrinterRow = () => {
      const vol = `${fmt(printerProfile.x_mm)} × ${fmt(printerProfile.y_mm)} × ${fmt(printerProfile.z_mm)} mm`;
      printerRow.replaceChildren();
      printerRow.append(el("span", "sd-summary-label", "Printer"), " ", el("span", "sd-summary-value", vol));
      if (lastSummary && !lastSummary.fits_printer) {
        printerRow.append(" ", el("span", "sd-fit-warning", ` — ${lastSummary.first_fit_error || "Does not fit your printer"}`));
      }
      if (callbacks.openPrinterSettings) {
        const change = el("button", "link-button", "Change…"); change.type = "button";
        change.addEventListener("click", () => callbacks.openPrinterSettings(), { signal: events.signal });
        printerRow.append(" ", change);
      }
    };
    updatePrinterRow();
    const drawersGroup = group(form, "Drawers"); drawersGroup.classList.add("sd-drawers-group");
    const count = input(block.drawers.length, "number"); count.min = String(minDrawers); count.max = String(maxDrawers); count.step = "1";
    count.id = `sd-count-${epoch}`;
    count.disabled = mode === "edit";
    const countNote = el("small", "sd-field-error"); countNote.hidden = true; countNote.id = `sd-count-note-${epoch}`;
    count.setAttribute("aria-describedby", countNote.id);
    const countField = labeled("Number of drawers", count,
      structural ? "Use Add Drawer or Delete below." : mode === "edit" ? "Add or remove drawers in Design." : null);
    countField.append(countNote);
    const fit = select(block.drawer_fit_mm, NAMED(rules.fitChoices, ["Tight", "Standard", "Loose"]));
    let previousFit = Number(fit.value);
    const handles = select(String(block.drawer_handles), [["true", "Pull handles"], ["false", "No handles"]]);
    const handleSize = select(block.drawer_handle_size, [["auto", "Auto"], ["small", "Small"], ["medium", "Medium"], ["large", "Large"]]);
    const handleField = labeled("Pull size", handleSize);
    const drawersRowA = el("div", "sd-size-grid");
    const fitField = labeled("Drawer fit", fit);
    fitField.title = "Standard is recommended for the first print. Tight leaves very little working clearance.";
    drawersRowA.append(countField, fitField);
    const drawersRowB = el("div", "sd-size-grid");
    drawersRowB.append(labeled("Handles", handles), handleField);
    drawersGroup.append(drawersRowA, drawersRowB);
    const drawerRows = el("div", "sd-drawer-rows"); drawersGroup.append(drawerRows);
    const cabinet = group(form, "Cabinet"); cabinet.classList.add("sd-cabinet-group");
    const style = select(block.cabinet_style, [["full", "Full"], ["open", "Open"]]);
    const rear = select(block.rear_support, [["cross", "Rear cross"], ["solid", "Rear solid"]]);
    const wallMounting = select(block.wall_mounting, [["off", "Off"], ["keyholes", "Keyholes"]]);
    const keyholeCount = select(String(block.wall_mount_keyholes_per_drawer), [["2", "2 — left and right"], ["4", "4 — two rows, left and right"]]);
    const keyholeCountField = labeled("Keyholes per drawer level", keyholeCount);
    keyholeCountField.title = "2 keyholes: one left and one right. 4 keyholes: left and right on two rows.";
    const stack = select(String(block.stacking), [["false", "Not stackable"], ["true", "Stackable"]]);
    const frame = select(block.open_frame_width_mm, NAMED(rules.frameChoices, ["Compact", "Standard", "Strong"]));
    const frameField = labeled("Open frame width", frame);
    const cabinetRowA = el("div", "sd-size-grid");
    cabinetRowA.append(labeled("Cabinet style", style),
      labeled("Rear support", rear),
      labeled("Wall mounting", wallMounting),
      keyholeCountField);
    const cabinetRowB = el("div", "sd-size-grid");
    cabinetRowB.append(labeled("Stacking", stack),
      frameField);
    cabinet.append(cabinetRowA, cabinetRowB);
    // Finish: labels + material in one area (Fix 117).
    const finish = group(form, "Finish"); finish.classList.add("sd-finish-group");
    const labels = el("div", "sd-subgroup"); labels.append(el("strong", "sd-subhead", "Labels"));
    const unitEnabled = select(String(block.unit_label_enabled), [["false", "Unit label off"], ["true", "Unit label on"]]);
    const unitText = input(block.unit_label_text); unitText.maxLength = labelLimit;
    unitText.id = `sd-unit-label-${epoch}`;
    unitText.dataset.heightNeutral = "1";
    const drawerEnabled = select(String(block.drawer_labels_enabled), [["false", "Drawer labels off"], ["true", "Drawer labels on"]]);
    const labelStyle = select(block.drawer_label_style, [["inlaid", "Inlaid"], ["raised", "Raised"]]);
    const unitTextField = labeled("Unit label text", unitText), styleField = labeled("Drawer label style", labelStyle);
    const labelsRowA = el("div", "sd-size-grid");
    labelsRowA.append(labeled("Unit label", unitEnabled), unitTextField);
    const labelsRowB = el("div", "sd-size-grid");
    labelsRowB.append(labeled("Drawer labels", drawerEnabled), styleField);
    labels.append(labelsRowA, labelsRowB);
    const material = el("div", "sd-subgroup"); material.append(el("strong", "sd-subhead", "Material")); const matA = el("div", "sd-material-three"), matB = el("div", "sd-material-two");
    material.append(matA, matB);
    const materialFields = {};
    for (const [key, title, row, kind] of [
      ["cabinet_wall_mm", "Cabinet wall thickness", matA, "wall_choices"], ["cabinet_base_mm", "Cabinet base thickness", matA, "base_choices"],
      ["cabinet_top_mm", "Cabinet top thickness", matA, "base_choices"], ["drawer_wall_mm", "Drawer wall thickness", matB, "wall_choices"],
      ["drawer_base_mm", "Drawer base thickness", matB, "base_choices"]]) {
      const control = select(block[key], materialChoices(catalog, kind, block[key])); materialFields[key] = control; row.append(labeled(title, control));
    }
    finish.append(labels, material);
    const summaryGroup = el("div", "sd-summary-compact sd-summary-group"); form.append(summaryGroup); const summary = el("div", "sd-summary", "Checking cabinet…"); summaryGroup.append(summary);
    const syncVisibility = () => {
      frameField.hidden = style.value !== "open"; handleField.hidden = handles.value !== "true";
      keyholeCountField.hidden = wallMounting.value !== "keyholes";
      unitTextField.hidden = unitEnabled.value !== "true"; styleField.hidden = drawerEnabled.value !== "true";
      // Fix 103 (Packet B): Basic Setup shows only Basics + Drawers.
      // Advanced controls are built but hidden, so draft() reads canonical
      // defaults for them exactly as before.
      if (scope === "basic") {
        cabinet.hidden = true; finish.hidden = true;
        fit.closest("label").hidden = true;
        handles.closest("label").hidden = true;
        handleField.hidden = true;
      }
    };
    let syncAddButton = () => {};
    let renderRowHeights = () => {};
    const heightInputs = new Map();
    const renderRows = () => {
      drawerRows.replaceChildren();
      heightInputs.clear();
      block.drawers.forEach((row, index) => {
        const line = el("div", `sd-drawer-row${drawerEnabled.value === "true" ? " sd-drawer-row-with-label" : ""}`);
        const head = el("div", "sd-drawer-head"); head.append(el("strong", "", `Drawer ${index + 1}`)); line.append(head);
        // Fix 103 Correction 1 (C2): full structural Design owns Add/Delete. The
        // buttons only ask the controller; the cabinet mutation authority
        // (SP.cabinetAdd / SP.cabinetDelete) does the work.
        if (structural && row.id && !String(row.id).startsWith("temporary:")) {
          const remove = el("button", "link-button sd-drawer-delete", "Delete"); remove.type = "button";
          remove.disabled = disabled || block.drawers.length <= 1;
          remove.title = block.drawers.length <= 1 ? "A cabinet keeps at least one drawer." : `Delete Drawer ${index + 1}`;
          remove.addEventListener("click", event => { event.stopPropagation(); callbacks.deleteDrawer?.(row.id); }, { signal: events.signal });
          head.append(remove);
        }
        // Fix 103 (Section E): click a drawer row to make it the active drawer
        // and highlight it in 3D. Rows without a stable saved id (temporary
        // keys) have no server owner, so they never highlight.
        if (structural && row.id && !String(row.id).startsWith("temporary:")) {
          const owner = `drawer:${row.id}`;
          line.dataset.drawerId = row.id;
          line.classList.toggle("sd-drawer-row-active", row.id === activeDrawerId);
          line.style.cursor = "pointer";
          line.setAttribute("role", "group");
          line.setAttribute("aria-label", `Drawer ${index + 1}. Click to highlight in 3D.`);
          line.addEventListener("click", event => {
            // Clicking into a field only selects the drawer; clicking the row
            // itself toggles the highlight.
            const inField = Boolean(event.target.closest?.("input, select, textarea, button"));
            selectDrawer(row.id);
            callbacks.onHighlightDrawer?.(owner, { ensure: inField });
          }, { signal: events.signal });
        }
        // Usable height never waits for summary or preview work.
        const height = input("", "number"); height.step = "any"; height.required = true;
        height.disabled = disabled;
        height.id = `sd-height-${epoch}-${index}`;
        height.dataset.usableHeight = "1";
        heightInputs.set(row, height);
        height.addEventListener("input", () => {
          if (!height.value.trim() || !Number.isFinite(setUsable(row, height.value))) row.height_mm = NaN;
          renderRowHeights(); syncHeightField(); schedule();
        }, { signal: events.signal });
        const label = input(row.label_text); label.maxLength = labelLimit; label.disabled = disabled;
        label.id = `sd-label-${epoch}-${index}`;
        label.dataset.heightNeutral = "1";
        label.addEventListener("input", () => { row.label_text = label.value; }, { signal: events.signal });
        const labelField = labeled("Label text", label); labelField.hidden = drawerEnabled.value !== "true";
        line.append(labeled("Usable height", height, null, "mm"), labelField);
        drawerRows.append(line);
      });
      renderRowHeights();
    };
    if (!compact) drawersGroup.append(help("Each height is the drawer's usable interior height."));
    if (structural) {
      const addRow = el("div", "sd-drawer-actions");
      const add = el("button", "button secondary", "Add Drawer"); add.type = "button";
      add.addEventListener("click", () => callbacks.addDrawer?.(), { signal: events.signal });
      addRow.append(add); drawersGroup.append(addRow);
      syncAddButton = () => {
        add.disabled = disabled || block.drawers.length >= maxDrawers;
        add.title = block.drawers.length >= maxDrawers ? `A cabinet holds at most ${maxDrawers} drawers.` : "";
      };
      syncAddButton();
    }
    let activeDrawerId = block.drawers.find(row => row.id && !String(row.id).startsWith("temporary:"))?.id || null;
    const roundMm = value => Math.round(value * 1000) / 1000;
    const getDrawerFitMm = () => Number(fit.value);
    const usableOf = row => roundMm(row.height_mm + getDrawerFitMm());
    const usableMinOf = () => roundMm(minDrawerHeight + getDrawerFitMm());
    const setUsable = (row, requested) => {
      const wanted = Number(requested);
      if (!Number.isFinite(wanted)) return NaN;
      row.height_mm = roundMm(wanted - getDrawerFitMm());
      return wanted;
    };
    const activeRow = () => block.drawers.find(row => row.id === activeDrawerId) || null;
    const isHeightField = node => Boolean(node?.dataset?.usableHeight);
    // Background validation cannot disable editing.
    renderRowHeights = () => {
      block.drawers.forEach(row => {
        const field = heightInputs.get(row);
        if (!field) return;
        const usable = usableOf(row);
        field.disabled = disabled;
        field.min = String(usableMinOf());
        field.toggleAttribute("aria-invalid", !Number.isFinite(usable) || usable < usableMinOf());
        if (document.activeElement !== field) field.value = Number.isFinite(usable) ? String(usable) : "";
      });
      syncAddButton();
    };
    const syncHeightField = () => {
      if (!structural) return;
      const row = activeRow(), index = block.drawers.indexOf(row);
      const usable = row ? usableOf(row) : NaN, ready = Number.isFinite(usable);
      zField.disabled = disabled || !row;
      zField.min = String(usableMinOf());
      zField.toggleAttribute("aria-invalid", Boolean(row) && (!ready || usable < usableMinOf()));
      if (document.activeElement !== zField) zField.value = ready ? String(usable) : "";
      zHelp.textContent = !row ? "Select a drawer" : `Drawer ${index + 1} usable height · minimum ${usableMinOf()} mm`;
    };
    const selectDrawer = id => {
      if (!structural || id === activeDrawerId || !block.drawers.some(row => row.id === id)) return;
      activeDrawerId = id;
      for (const node of drawerRows.querySelectorAll(".sd-drawer-row")) {
        node.classList.toggle("sd-drawer-row-active", node.dataset.drawerId === id);
      }
      // The already-current summary holds every drawer: no waiting on selection.
      syncHeightField();
    };
    // Typed input, arrow/wheel steps and the 3D handles all land here.
    const setInterior = (axis, requested) => {
      if (axis === "z") {
        const row = activeRow();
        if (!row) return NaN;
        const applied = setUsable(row, requested);
        if (!Number.isFinite(applied)) row.height_mm = NaN;
        renderRowHeights(); syncHeightField(); schedule();
        return applied;
      }
      const field = axis === "x" ? x : y;
      field.value = String(requested);
      formatMm(field); schedule();
      const resolved = resolveMm(field);
      return resolved.ok ? resolved.mm : NaN;
    };
    const getInterior = () => {
      const row = activeRow();
      return {
        x: resolveMm(x).ok ? resolveMm(x).mm : NaN,
        y: resolveMm(y).ok ? resolveMm(y).mm : NaN,
        z: row ? usableOf(row) : NaN,
      };
    };
    const draft = () => {
      const next = copy(space), b = next.storage_drawers;
      const resolvedX = resolveMm(x), resolvedY = resolveMm(y);
      next.name = name.value.trim(); next.x = resolvedX.mm; next.y = resolvedY.mm;
      b.drawers = copy(block.drawers); b.cabinet_style = style.value; b.rear_support = rear.value;
      b.wall_mounting = wallMounting.value;
      b.wall_mount_keyholes_per_drawer = Number(keyholeCount.value);
      b.open_frame_width_mm = Number(frame.value); b.drawer_fit_mm = Number(fit.value);
      b.stacking = stack.value === "true"; b.drawer_handles = handles.value === "true"; b.drawer_handle_size = handleSize.value;
      b.unit_label_enabled = unitEnabled.value === "true"; b.unit_label_text = unitText.value;
      b.drawer_labels_enabled = drawerEnabled.value === "true"; b.drawer_label_style = labelStyle.value;
      for (const [key, control] of Object.entries(materialFields)) b[key] = Number(control.value);
      next.z = b.drawers.reduce((sum, row) => sum + row.height_mm, 0); return next;
    };
    const countProblem = () => {
      const wanted = Number(count.value);
      return count.value.trim() === "" || !Number.isInteger(wanted) || wanted < minDrawers || wanted > maxDrawers
        ? `Enter ${minDrawers}–${maxDrawers}` : "";
    };
    const readFields = () => {
      const fail = (message, focusId) => ({ ok: false, message, focusId });
      if (!name.value.trim()) return fail("Enter a Space name", name.id);
      for (const [field, axis] of [[x, "Width"], [y, "Depth"]]) {
        if (!resolveMm(field).ok) return fail(`${axis} must be ${minUnits * baseUnit}–${maxUnits * baseUnit} mm (${baseUnit} mm grid).`, field.id);
      }
      if (countProblem()) return fail(`Number of drawers: ${countProblem().toLowerCase()}`, count.id);
      for (let i = 0; i < block.drawers.length; i++) {
        const height = block.drawers[i].height_mm;
        if (!Number.isFinite(height) || height < minDrawerHeight) {
          const floor = usableMinOf();
          return fail(Number.isFinite(floor) ? `Drawer ${i + 1} needs at least ${fmt(floor)} mm usable height` : `Drawer ${i + 1} is too short`, `sd-height-${epoch}-${i}`);
        }
      }
      if (unitEnabled.value === "true" && !unitText.value.trim()) return fail("Enter unit label text", unitText.id);
      if (unitText.value.length > labelLimit) return fail("Shorten the unit label", unitText.id);
      if (drawerEnabled.value === "true") {
        for (let i = 0; i < block.drawers.length; i++) {
          if ((block.drawers[i].label_text || "").length > labelLimit) return fail(`Shorten Drawer ${i + 1}'s label`, `sd-label-${epoch}-${i}`);
        }
      }
      return { ok: true, spaceDraft: draft() };
    };
    const read = () => {
      const fields = readFields();
      if (!fields.ok) return fields;
      if (summaryState === "pending") return { ok: false, message: "Checking cabinet…", focusId: null, pending: true };
      if (summaryState === "error") return { ok: false, message: summaryError, focusId: null };
      if (summaryIdentity !== (callbacks.identity?.() ?? space.id ?? space.name) ||
          summaryKey !== window.StorageDrawers.structuralDraftKey(fields.spaceDraft, printerProfile)) {
        return { ok: false, message: "Checking cabinet…", focusId: null, pending: true };
      }
      // Fix 103 (Packet B): known printer oversize is a non-blocking warning
      // (shown beside the Printer row in Size). Only unknown / stale / error
      // still blocks, via the summaryState checks above.
      return fields;
    };
    const notifyReady = () => {
      const fields = readFields();
      const identity = callbacks.identity?.() ?? space.id ?? space.name;
      const ready = Boolean(fields.ok && summaryState === "ok" && summaryIdentity === identity &&
        summaryKey === window.StorageDrawers.structuralDraftKey(fields.spaceDraft, printerProfile));
      if (ready !== lastReady) { lastReady = ready; onReadyChange?.(ready); }
    };
    const line = (label, value, className = "") => {
      const row = el("p", `sd-summary-line ${className}`.trim());
      row.append(el("span", "sd-summary-label", label), " ", el("span", "sd-summary-value", value)); return row;
    };
    const showSummary = response => {
      lastSummary = response;
      const outside = (response.outside_xyz || []).map(v => fmt(v));
      const [fx, fy] = (response.field_mm || []).map(v => fmt(v));
      const heights = (response.drawers || []).map(row => fmt(row.usable_height_mm)).join(", ");
      const material = response.effective_material || {};
      const lines = [
        line("Finished outside", `${outside.join(" × ")} mm`, "sd-summary-outside"),
        line("Inside each drawer", `${fx} × ${fy} mm`),
        line("Drawers", `${response.drawer_count} · usable height${response.drawer_count === 1 ? "" : "s"} ${heights} mm`),
        line("Cabinet base / top", `${fmt(material.base_mm)} / ${fmt(material.top_mm)} mm`),
      ];
      if (response.cabinet_style === "open" && material.frame_width_mm) lines.push(line("Open frame width", `${fmt(material.frame_width_mm)} mm`));
      for (const warning of response.warnings || []) lines.push(el("p", "sd-summary-warning", `Note: ${warning}`));
      const guide = el("p", "sd-summary-line");
      const link = el("a", "", "Assembly & print guide"); link.href = GUIDE_URL; link.target = "_blank"; link.rel = "noopener";
      guide.append(link); lines.push(guide);
      summary.replaceChildren(...lines);
      updatePrinterRow();
      renderRowHeights();
      syncHeightField();
      callbacks.onSummary?.(response);
    };
    const showSummaryText = (text, bad = false) => { summary.replaceChildren(el("p", bad ? "sd-fit-verdict bad" : "sd-summary-line", text)); updatePrinterRow(); };
    const schedule = () => {
      formatMm(x); formatMm(y);
      summaryState = "pending"; summaryError = ""; summaryKey = null; summaryIdentity = null; lastSummary = null; showSummaryText("Checking cabinet…"); notifyReady();
      renderRowHeights();
      syncHeightField();
      callbacks.onChange?.();
      clearTimeout(timer); const n = ++requestNumber; const identity = callbacks.identity?.() ?? space.id ?? space.name;
      const pEpoch = profileEpoch; const checked = readFields();
      if (!checked.ok) { summaryState = "error"; summaryError = checked.message; showSummaryText(checked.message, true); notifyReady(); markSettled(); return; }
      const next = checked.spaceDraft;
      const key = window.StorageDrawers.structuralDraftKey(next, printerProfile);
      timer = setTimeout(async () => {
        try {
          const preview = copy(next);
          for (const row of preview.storage_drawers.drawers) {
            if (!row.id) row.id = row.temp_key?.slice("temporary:".length) || crypto.randomUUID();
          }
          let timeout;
          let response;
          try {
            response = await Promise.race([
              callbacks.requestSummary({ space: preview, printer_profile: printerProfile }),
              new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error("Cabinet check timed out. Edit a setting or retry.")), 30000); }),
            ]);
          } finally { clearTimeout(timeout); }
          if (!live || epoch !== mountSerial || n !== requestNumber || pEpoch !== profileEpoch || identity !== (callbacks.identity?.() ?? space.id ?? space.name) || key !== window.StorageDrawers.structuralDraftKey(draft(), printerProfile)) return;
          showSummary(response); summaryKey = key; summaryIdentity = identity; summaryState = "ok"; notifyReady(); markSettled();
        } catch (error) {
          if (live && epoch === mountSerial && n === requestNumber && pEpoch === profileEpoch && identity === (callbacks.identity?.() ?? space.id ?? space.name) && key === window.StorageDrawers.structuralDraftKey(draft(), printerProfile)) {
            summaryError = friendlyError(error) || "Cabinet is invalid"; showSummaryText(summaryError, true); summaryState = "error"; notifyReady(); markSettled();
          }
        }
      }, 250);
    };
    // The entered count stays visible while it is wrong; a range note explains it.
    const applyCount = () => {
      const problem = countProblem();
      countNote.hidden = !problem; countNote.textContent = problem;
      count.toggleAttribute("aria-invalid", Boolean(problem));
      if (problem) { schedule(); return; }
      const wanted = Number(count.value);
      while (block.drawers.length > wanted) tail.unshift(block.drawers.pop());
      while (block.drawers.length < wanted) block.drawers.push(tail.shift() || { temp_key: `temporary:${crypto.randomUUID()}`, height_mm: block.drawers.at(-1)?.height_mm ?? (rules.defaultHeight - Number(fit.value)), label_text: "" });
      renderRows(); schedule();
    };
    count.addEventListener("input", applyCount, { signal: events.signal });
    fit.addEventListener("change", () => {
      const nextFit = Number(fit.value);
      for (const row of block.drawers) {
        const oldUsable = roundMm(row.height_mm + previousFit);
        row.height_mm = roundMm(oldUsable - nextFit);
      }
      previousFit = nextFit;
      renderRowHeights(); syncHeightField(); schedule();
    }, { signal: events.signal });
    form.addEventListener("input", event => {
      if (event.target !== count && event.target !== fit && !isHeightField(event.target)) schedule();
    }, { signal: events.signal });
    form.addEventListener("change", event => {
      if (event.target !== count && event.target !== fit && !isHeightField(event.target)) {
        syncVisibility(); renderRows(); schedule();
      }
    }, { signal: events.signal });
    if (structural) {
      zField.addEventListener("input", () => { setInterior("z", zField.value.trim() ? Number(zField.value) : NaN); }, { signal: events.signal });
      for (const [axis, field] of [["x", x], ["y", y], ["z", zField]]) {
        const step = axis === "z" ? 1 : baseUnit;
        const current = () => (axis === "z" ? Number(zField.value) : (resolveMm(field).ok ? resolveMm(field).mm : NaN));
        field.addEventListener("keydown", event => {
          if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
          event.preventDefault();
          if (Number.isFinite(current())) setInterior(axis, current() + (event.key === "ArrowUp" ? step : -step));
        }, { signal: events.signal });
        field.addEventListener("wheel", event => {
          if (document.activeElement !== field) return;
          event.preventDefault();
          if (Number.isFinite(current())) setInterior(axis, current() + (event.deltaY < 0 ? step : -step));
        }, { signal: events.signal, passive: false });
      }
    }
    const snapshotValue = field => {
      const resolved = resolveMm(field);
      return resolved.ok ? resolved.mm : `invalid:${field.value}`;
    };
    formatMm(x); formatMm(y);
    const snapshot = () => JSON.stringify([
      name.value.trim(), snapshotValue(x), snapshotValue(y), count.value,
      block.drawers.map(row => [row.id || "", row.height_mm, row.label_text]),
      style.value, rear.value, wallMounting.value, keyholeCount.value,
      stack.value, frame.value, fit.value, handles.value, handleSize.value,
      unitEnabled.value, unitText.value, drawerEnabled.value, labelStyle.value,
      Object.values(materialFields).map(control => control.value)]);
    syncVisibility(); renderRows(); schedule();
    let baseline = snapshot();
    return {
      read,
      // Resolves when the in-flight live validation settles (ok or error),
      // or after timeoutMs with validation still pending. Lets Create/Save
      // wait for a check that was mid-flight instead of failing on it.
      whenValidationSettled(timeoutMs = 30000) {
        return new Promise(resolve => {
          if (summaryState !== "pending") return resolve();
          const done = () => { clearTimeout(waitTimer); resolve(); };
          const waitTimer = setTimeout(() => {
            if (summaryState === "pending") {
              ++requestNumber; clearTimeout(timer);
              summaryState = "error"; summaryError = "Cabinet check timed out. Edit a setting or retry.";
              showSummaryText(summaryError, true); notifyReady(); markSettled();
            }
            settleWaiters = settleWaiters.filter(fn => fn !== done); resolve();
          }, timeoutMs);
          settleWaiters.push(done);
        });
      },
      isDirty: () => snapshot() !== baseline,
      markPristine() { baseline = snapshot(); },
      // Fix 103 (R2): the unsaved draft Space, available even while the live
      // summary is still pending (the preview consumes this, never the
      // accepted Space). Returns the same shape as read(), minus summary gating.
      draft: () => readFields(),
      currentSummary: () => (summaryState === "ok" ? lastSummary : null),
      getInterior, setInterior, selectDrawer,
      activeDrawerId: () => activeDrawerId,
      setPrinterProfile(next) { printerProfile = copy(next); profileEpoch += 1; schedule(); },
      refreshSummary() { schedule(); },
      setDisabled(value) {
        disabled = !!value;
        for (const control of form.querySelectorAll("input, select")) control.disabled = disabled;
        if (!disabled) count.disabled = mode === "edit";
        renderRows();
        syncHeightField();
      },
      destroy() { live = false; mountSerial += 1; clearTimeout(timer); events.abort(); markSettled(); host.replaceChildren(); }
    };
  };
  window.StorageDrawersForm = { mount };
})();
