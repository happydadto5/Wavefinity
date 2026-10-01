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
  const group = (host, title) => { const section = el("section", "sd-form-group"); section.append(el("h3", "", title)); host.append(section); return section; };
  const materialChoices = (catalog, kind, current) => {
    const rows = catalog?.b4b_rules?.[kind] || [];
    const options = rows.map(row => Array.isArray(row) ? [String(row[0]), String(row[1])] : [String(row.value ?? row.mm), String(row.label ?? row.name)]);
    if (!options.some(row => Number(row[0]) === Number(current))) options.push([String(current), `${current} mm — Existing`]);
    return options;
  };
  const NAMED = (list, names, unit = "mm") => list.map((mm, index) => [String(mm),
    list.length === names.length ? `${names[index]} · ${mm.toFixed(2).replace(/\.?0+$/, "")} ${unit}` : `${mm} ${unit}`]);
  const mount = ({ host, initialSpace, catalog, printerProfile, mode, callbacks = {} }) => {
    const epoch = ++mountSerial;
    const rules = window.StorageDrawers.catalogRules(catalog);
    const { baseUnit, minDrawerHeight, minUnits, maxUnits, minDrawers, maxDrawers, labelLimit } = rules;
    const defaults = () => ({
      drawers: Array.from({ length: 3 }, () => ({ temp_key: `temporary:${crypto.randomUUID()}`, height_mm: rules.defaultHeight, label_text: "" })),
      cabinet_style: "full", rear_support: "cross", open_frame_width_mm: rules.defaultFrame, drawer_fit_mm: rules.defaultFit,
      wall_mounting: "off", wall_mount_keyholes_per_drawer: 2,
      drawer_handles: true, drawer_handle_size: "auto", stacking: false,
      unit_label_enabled: false, unit_label_text: "", drawer_labels_enabled: false, drawer_label_style: "inlaid",
      cabinet_wall_mm: 1.6, cabinet_base_mm: 1.6, cabinet_top_mm: 1.6, drawer_wall_mm: 1.6, drawer_base_mm: 1.6,
    });
    let live = true, timer = null, requestNumber = 0, profileEpoch = 0;
    const events = new AbortController();
    let summaryState = "pending", summaryError = "", summaryKey = null, summaryIdentity = null, disabled = false, lastSummary = null;
    // Waiters for the in-flight live validation (Create/Save clicked while
    // the cabinet check is pending): resolved when the check settles.
    let settleWaiters = [];
    const markSettled = () => {
      if (!settleWaiters.length) return;
      const waiters = settleWaiters; settleWaiters = [];
      for (const done of waiters) { try { done(); } catch { /* a waiter must never break validation */ } }
    };
    const space = copy(initialSpace || { kind: "storage_drawers", name: "", x: minUnits * baseUnit, y: minUnits * baseUnit });
    space.storage_drawers = { ...defaults(), ...copy(space.storage_drawers || {}) };
    const block = space.storage_drawers;
    const tail = [];
    host.replaceChildren();
    const form = el("div", "sd-form"); host.append(form);
    const nameGroup = group(form, "Name");
    const name = input(space.name); name.maxLength = 80; name.required = true;
    name.id = `sd-name-${epoch}`;
    nameGroup.append(labeled("Space name", name));
    const sizeGroup = group(form, "Size"); const sizeGrid = el("div", "sd-size-grid"); sizeGroup.append(sizeGrid);
    const x = input(space.x / baseUnit, "number"), y = input(space.y / baseUnit, "number");
    x.id = `sd-x-${epoch}`; y.id = `sd-y-${epoch}`;
    for (const field of [x, y]) { field.min = String(minUnits); field.max = String(maxUnits); field.step = "1"; field.required = true; }
    sizeGrid.append(labeled("X units", x, "X = left ↔ right."), labeled("Y units", y, "Y = front ↔ back."));
    sizeGroup.append(help(`1 unit = ${baseUnit} mm. Measure the space you want inside each drawer, then divide by ${baseUnit}.`));
    const drawersGroup = group(form, "Drawers");
    const count = input(block.drawers.length, "number"); count.min = String(minDrawers); count.max = String(maxDrawers); count.step = "1";
    count.id = `sd-count-${epoch}`;
    count.disabled = mode === "edit";
    const countNote = el("small", "sd-field-error"); countNote.hidden = true; countNote.id = `sd-count-note-${epoch}`;
    count.setAttribute("aria-describedby", countNote.id);
    const countField = labeled("Number of drawers", count, mode === "edit" ? "Add or remove drawers from the cabinet panel." : null);
    countField.append(countNote);
    const fit = select(block.drawer_fit_mm, NAMED(rules.fitChoices, ["Tight", "Standard", "Loose"]));
    const handles = select(String(block.drawer_handles), [["true", "Pull handles"], ["false", "No handles"]]);
    const handleSize = select(block.drawer_handle_size, [["auto", "Auto"], ["small", "Small"], ["medium", "Medium"], ["large", "Large"]]);
    const handleField = labeled("Pull size", handleSize);
    const drawersRowA = el("div", "sd-size-grid");
    drawersRowA.append(countField,
      labeled("Drawer fit", fit, "Changes drawer-to-cabinet clearance only. Cabinet joints keep their own fixed engineering clearance. Tight leaves the drawer catch almost no working margin — print your first cabinet on Standard."));
    const drawersRowB = el("div", "sd-size-grid");
    drawersRowB.append(labeled("Handles", handles), handleField);
    drawersGroup.append(drawersRowA, drawersRowB);
    const drawerRows = el("div", "sd-drawer-rows"); drawersGroup.append(drawerRows);
    const cabinet = group(form, "Cabinet");
    const style = select(block.cabinet_style, [["full", "Full"], ["open", "Open"]]);
    const rear = select(block.rear_support, [["cross", "Rear cross"], ["solid", "Rear solid"]]);
    const wallMounting = select(block.wall_mounting, [["off", "Off"], ["keyholes", "Keyholes"]]);
    const keyholeCount = select(String(block.wall_mount_keyholes_per_drawer), [["2", "2"], ["4", "4"]]);
    const keyholeCountField = labeled(
      "Keyholes per drawer level", keyholeCount,
      "2 = left/right. 4 = left/right at upper and lower mounting rows."
    );
    const stack = select(String(block.stacking), [["false", "Not stackable"], ["true", "Stackable"]]);
    const frame = select(block.open_frame_width_mm, NAMED(rules.frameChoices, ["Compact", "Standard", "Strong"]));
    const frameField = labeled("Open frame width", frame);
    const cabinetRowA = el("div", "sd-size-grid");
    cabinetRowA.append(labeled("Cabinet style", style,
        "Full: enclosed side-panel cabinet around the drawer stack. Open: open-frame sides/rails with less panel material."),
      labeled("Rear support", rear, "Rear Cross: lighter cross-brace rear support. Rear Solid: full rear panel."),
      labeled("Wall mounting", wallMounting, "Adds reinforced keyhole slots to the cabinet back at every drawer level."),
      keyholeCountField);
    const cabinetRowB = el("div", "sd-size-grid");
    cabinetRowB.append(labeled("Stacking", stack, "Stackable adds top/bottom stacking interfaces and four separate stacking pegs."),
      frameField);
    cabinet.append(cabinetRowA, cabinetRowB);
    const labels = group(form, "Labels");
    const unitEnabled = select(String(block.unit_label_enabled), [["false", "Unit label off"], ["true", "Unit label on"]]);
    const unitText = input(block.unit_label_text); unitText.maxLength = labelLimit;
    unitText.id = `sd-unit-label-${epoch}`;
    const drawerEnabled = select(String(block.drawer_labels_enabled), [["false", "Drawer labels off"], ["true", "Drawer labels on"]]);
    const labelStyle = select(block.drawer_label_style, [["inlaid", "Inlaid"], ["raised", "Raised"]]);
    const unitTextField = labeled("Unit label text", unitText), styleField = labeled("Drawer label style", labelStyle);
    const labelsRowA = el("div", "sd-size-grid");
    labelsRowA.append(labeled("Unit label", unitEnabled), unitTextField);
    const labelsRowB = el("div", "sd-size-grid");
    labelsRowB.append(labeled("Drawer labels", drawerEnabled), styleField);
    labels.append(labelsRowA, labelsRowB);
    const material = group(form, "Material"); const matA = el("div", "sd-material-three"), matB = el("div", "sd-material-two");
    material.append(matA, matB);
    const materialFields = {};
    for (const [key, title, row, kind] of [
      ["cabinet_wall_mm", "Cabinet wall thickness", matA, "wall_choices"], ["cabinet_base_mm", "Cabinet base thickness", matA, "base_choices"],
      ["cabinet_top_mm", "Cabinet top thickness", matA, "base_choices"], ["drawer_wall_mm", "Drawer wall thickness", matB, "wall_choices"],
      ["drawer_base_mm", "Drawer base thickness", matB, "base_choices"]]) {
      const control = select(block[key], materialChoices(catalog, kind, block[key])); materialFields[key] = control; row.append(labeled(title, control));
    }
    const summaryGroup = group(form, "Summary"); const summary = el("div", "sd-summary", "Checking cabinet…"); summaryGroup.append(summary);
    const syncVisibility = () => {
      frameField.hidden = style.value !== "open"; handleField.hidden = handles.value !== "true";
      keyholeCountField.hidden = wallMounting.value !== "keyholes";
      unitTextField.hidden = unitEnabled.value !== "true"; styleField.hidden = drawerEnabled.value !== "true";
    };
    const renderRows = () => {
      drawerRows.replaceChildren();
      block.drawers.forEach((row, index) => {
        const line = el("div", "sd-drawer-row"); line.append(el("strong", "", `Drawer ${index + 1}`));
        const height = input(row.height_mm, "number"); height.min = String(minDrawerHeight); height.step = "any"; height.required = true;
        height.disabled = disabled;
        height.id = `sd-height-${epoch}-${index}`;
        height.addEventListener("input", () => { row.height_mm = Number(height.value); }, { signal: events.signal });
        const label = input(row.label_text); label.maxLength = labelLimit; label.disabled = disabled;
        label.id = `sd-label-${epoch}-${index}`;
        label.addEventListener("input", () => { row.label_text = label.value; }, { signal: events.signal });
        const labelField = labeled("Label text", label); labelField.hidden = drawerEnabled.value !== "true";
        line.append(labeled(
          "Drawer height", height,
          "Physical usable bin height also includes the selected Drawer fit and is shown in Summary.",
          "mm"
        ), labelField);
        drawerRows.append(line);
      });
    };
    const draft = () => {
      const next = copy(space), b = next.storage_drawers;
      next.name = name.value.trim(); next.x = Number(x.value) * baseUnit; next.y = Number(y.value) * baseUnit;
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
      for (const [field, axis] of [[x, "X"], [y, "Y"]]) {
        const units = Number(field.value);
        if (field.value.trim() === "" || !Number.isInteger(units) || units < minUnits || units > maxUnits) return fail(`${axis} must be ${minUnits}–${maxUnits} whole units`, field.id);
      }
      if (countProblem()) return fail(`Number of drawers: ${countProblem().toLowerCase()}`, count.id);
      for (let i = 0; i < block.drawers.length; i++) {
        const height = block.drawers[i].height_mm;
        if (!Number.isFinite(height) || height < minDrawerHeight) return fail(`Drawer ${i + 1} needs at least ${minDrawerHeight} mm usable height`, `sd-height-${epoch}-${i}`);
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
      // The live summary is the printer-fit authority: a cabinet that cannot
      // print on the current printer is stopped here, not at Save Cabinet.
      if (lastSummary && !lastSummary.fits_printer) {
        return { ok: false, message: lastSummary.first_fit_error || "This cabinet does not fit the printer.", focusId: null };
      }
      return fields;
    };
    const line = (label, value, className = "") => {
      const row = el("p", `sd-summary-line ${className}`.trim());
      row.append(el("span", "sd-summary-label", label), " ", el("span", "sd-summary-value", value)); return row;
    };
    const showSummary = response => {
      lastSummary = response;
      const outside = (response.outside_xyz || []).map(v => fmt(v));
      const [ux, uy] = response.field_units || [];
      const [fx, fy] = (response.field_mm || []).map(v => fmt(v));
      const heights = (response.drawers || []).map(row => fmt(row.height_mm)).join(", ");
      const material = response.effective_material || {};
      const printer = `${fmt(printerProfile.x_mm)} × ${fmt(printerProfile.y_mm)} × ${fmt(printerProfile.z_mm)} mm`;
      const fitRow = el("p", `sd-fit-verdict ${response.fits_printer ? "ok" : "bad"}`,
        response.fits_printer ? "✓ Fits your printer" : `✗ ${response.first_fit_error || "Does not fit your printer"}`);
      const lines = [
        fitRow,
        line("Finished outside", `${outside.join(" × ")} mm`, "sd-summary-outside"),
        line("Field size", `${ux} × ${uy} units (${fx} × ${fy} mm) in each drawer`),
        line("Drawers", `${response.drawer_count} · usable height${response.drawer_count === 1 ? "" : "s"} ${heights} mm`),
        line("Cabinet base / top", `${fmt(material.base_mm)} / ${fmt(material.top_mm)} mm`),
      ];
      if (response.cabinet_style === "open" && material.frame_width_mm) lines.push(line("Open frame width", `${fmt(material.frame_width_mm)} mm`));
      const printerRow = line("Printer build volume", printer);
      if (callbacks.openPrinterSettings) {
        const change = el("button", "link-button", "Printer Settings…"); change.type = "button";
        change.addEventListener("click", () => callbacks.openPrinterSettings(), { signal: events.signal });
        printerRow.append(" ", change);
      }
      lines.push(printerRow);
      for (const warning of response.warnings || []) lines.push(el("p", "sd-summary-warning", `Note: ${warning}`));
      const guide = el("p", "sd-summary-line");
      const link = el("a", "", "Assembly & print guide"); link.href = GUIDE_URL; link.target = "_blank"; link.rel = "noopener";
      guide.append(link); lines.push(guide);
      summary.replaceChildren(...lines);
    };
    const showSummaryText = (text, bad = false) => { summary.replaceChildren(el("p", bad ? "sd-fit-verdict bad" : "sd-summary-line", text)); };
    const schedule = () => {
      summaryState = "pending"; summaryError = ""; summaryKey = null; summaryIdentity = null; lastSummary = null; showSummaryText("Checking cabinet…");
      clearTimeout(timer); const n = ++requestNumber; const identity = callbacks.identity?.() ?? space.id ?? space.name;
      const pEpoch = profileEpoch; const checked = readFields();
      if (!checked.ok) { summaryState = "error"; summaryError = checked.message; showSummaryText(checked.message, true); markSettled(); return; }
      const next = checked.spaceDraft;
      const key = window.StorageDrawers.structuralDraftKey(next, printerProfile);
      timer = setTimeout(async () => {
        try {
          const preview = copy(next);
          for (const row of preview.storage_drawers.drawers) {
            if (!row.id) row.id = row.temp_key?.slice("temporary:".length) || crypto.randomUUID();
          }
          const response = await callbacks.requestSummary({ space: preview, printer_profile: printerProfile });
          if (!live || epoch !== mountSerial || n !== requestNumber || pEpoch !== profileEpoch || identity !== (callbacks.identity?.() ?? space.id ?? space.name) || key !== window.StorageDrawers.structuralDraftKey(draft(), printerProfile)) return;
          showSummary(response); summaryKey = key; summaryIdentity = identity; summaryState = "ok"; markSettled();
        } catch (error) {
          if (live && epoch === mountSerial && n === requestNumber && pEpoch === profileEpoch && identity === (callbacks.identity?.() ?? space.id ?? space.name) && key === window.StorageDrawers.structuralDraftKey(draft(), printerProfile)) {
            summaryError = friendlyError(error) || "Cabinet is invalid"; showSummaryText(summaryError, true); summaryState = "error"; markSettled();
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
      while (block.drawers.length < wanted) block.drawers.push(tail.shift() || { temp_key: `temporary:${crypto.randomUUID()}`, height_mm: block.drawers.at(-1)?.height_mm || rules.defaultHeight, label_text: "" });
      renderRows(); schedule();
    };
    count.addEventListener("input", applyCount, { signal: events.signal });
    form.addEventListener("input", event => { if (event.target !== count) schedule(); }, { signal: events.signal });
    form.addEventListener("change", event => {
      if (event.target !== count) { syncVisibility(); renderRows(); schedule(); }
    }, { signal: events.signal });
    const snapshot = () => JSON.stringify([
      name.value.trim(), x.value, y.value, count.value,
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
            settleWaiters = settleWaiters.filter(fn => fn !== done);
            resolve();
          }, timeoutMs);
          settleWaiters.push(done);
        });
      },
      isDirty: () => snapshot() !== baseline,
      markPristine() { baseline = snapshot(); },
      setPrinterProfile(next) { printerProfile = copy(next); profileEpoch += 1; schedule(); },
      refreshSummary() { schedule(); },
      setDisabled(value) {
        disabled = !!value;
        for (const control of form.querySelectorAll("input, select")) control.disabled = disabled;
        if (!disabled) count.disabled = mode === "edit";
      },
      destroy() { live = false; mountSerial += 1; clearTimeout(timer); events.abort(); host.replaceChildren(); }
    };
  };
  window.StorageDrawersForm = { mount };
})();
