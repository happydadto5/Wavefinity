/* Create/Edit cabinet draft. No route or persistence calls live here. */
(() => {
  "use strict";
  let mountSerial = 0;
  const copy = value => structuredClone(value);
  const defaults = () => ({ drawers: Array.from({ length: 3 }, () => ({ temp_key: `temporary:${crypto.randomUUID()}`, height_mm: 40, label_text: "" })),
    cabinet_style: "full", rear_support: "cross", open_frame_width_mm: 14, drawer_fit_mm: 0.4,
    drawer_handles: true, drawer_handle_size: "auto", stacking: false,
    unit_label_enabled: false, unit_label_text: "", drawer_labels_enabled: false, drawer_label_style: "inlaid",
    cabinet_wall_mm: 1.6, cabinet_base_mm: 1.6, cabinet_top_mm: 1.6, drawer_wall_mm: 1.6, drawer_base_mm: 1.6 });
  const el = (tag, className = "", text = "") => {
    const node = document.createElement(tag); node.className = className; node.textContent = text; return node;
  };
  const labeled = (title, input) => { const label = el("label", "sd-field", title); label.append(input); return label; };
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
    if (!options.some(row => Number(row[0]) === Number(current))) options.push([String(current), `${current} mm (custom)`]);
    return options;
  };
  const mount = ({ host, initialSpace, catalog, printerProfile, mode, callbacks = {} }) => {
    const epoch = ++mountSerial;
    const baseUnit = catalog?.base_unit;
    const minDrawerHeight = catalog?.drawer_rules?.ordinary_bin_min_height_mm;
    if (typeof baseUnit !== "number" || !Number.isFinite(baseUnit) || baseUnit <= 0 ||
        typeof minDrawerHeight !== "number" || !Number.isFinite(minDrawerHeight) || minDrawerHeight <= 0) {
      throw new Error("Storage Drawers catalog rules are unavailable");
    }
    let live = true, timer = null, requestNumber = 0, profileEpoch = 0;
    const events = new AbortController();
    let summaryState = "pending", summaryError = "", summaryKey = null, summaryIdentity = null, disabled = false;
    const space = copy(initialSpace || { kind: "storage_drawers", name: "", x: 6 * baseUnit, y: 6 * baseUnit });
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
    for (const field of [x, y]) { field.min = "6"; field.max = "250"; field.step = "1"; field.required = true; }
    sizeGrid.append(labeled("X units", x), labeled("Y units", y));
    const drawersGroup = group(form, "Drawers");
    const count = input(block.drawers.length, "number"); count.min = "1"; count.max = "32"; count.step = "1";
    count.id = `sd-count-${epoch}`;
    count.disabled = mode === "edit";
    drawersGroup.append(labeled("Number drawers", count));
    const drawerRows = el("div", "sd-drawer-rows"); drawersGroup.append(drawerRows);
    const cabinet = group(form, "Cabinet");
    const style = select(block.cabinet_style, [["full","Full"],["open","Open"]]);
    const rear = select(block.rear_support, [["cross","Cross"],["solid","Solid"]]);
    const stack = select(String(block.stacking), [["false","Not stackable"],["true","Stackable"]]);
    const frame = select(block.open_frame_width_mm, [["10","Compact · 10 mm"],["14","Standard · 14 mm"],["18","Strong · 18 mm"]]);
    const handles = select(String(block.drawer_handles), [["true","Pull handles"],["false","No handles"]]);
    const handleSize = select(block.drawer_handle_size, [["auto","Auto"],["small","Small"],["medium","Medium"],["large","Large"]]);
    const fit = select(block.drawer_fit_mm, [["0.3","Tight · 0.30 mm"],["0.4","Standard · 0.40 mm"],["0.6","Loose · 0.60 mm"]]);
    const frameField = labeled("Open frame width", frame), handleField = labeled("Pull size", handleSize);
    cabinet.append(labeled("Cabinet style", style), labeled("Rear support", rear), labeled("Stacking", stack), frameField,
      labeled("Drawer fit", fit), labeled("Handles", handles), handleField);
    const labels = group(form, "Labels");
    const unitEnabled = select(String(block.unit_label_enabled), [["false","Unit label Off"],["true","Unit label On"]]);
    const unitText = input(block.unit_label_text); unitText.maxLength = 80;
    unitText.id = `sd-unit-label-${epoch}`;
    const drawerEnabled = select(String(block.drawer_labels_enabled), [["false","Drawer labels Off"],["true","Drawer labels On"]]);
    const labelStyle = select(block.drawer_label_style, [["inlaid","Inlaid"],["raised","Raised"]]);
    const unitTextField = labeled("Unit label text", unitText), styleField = labeled("Drawer label style", labelStyle);
    labels.append(labeled("Unit label", unitEnabled), unitTextField, labeled("Drawer labels", drawerEnabled), styleField);
    const material = group(form, "Material"); const matA = el("div", "sd-material-three"), matB = el("div", "sd-material-two");
    material.append(matA, matB);
    const materialFields = {};
    for (const [key, title, row, kind] of [
      ["cabinet_wall_mm","Cabinet wall",matA,"wall_choices"], ["cabinet_base_mm","Cabinet base",matA,"base_choices"],
      ["cabinet_top_mm","Cabinet top",matA,"base_choices"], ["drawer_wall_mm","Drawer wall",matB,"wall_choices"],
      ["drawer_base_mm","Drawer base",matB,"base_choices"]]) {
      const control = select(block[key], materialChoices(catalog, kind, block[key])); materialFields[key] = control; row.append(labeled(title, control));
    }
    const summaryGroup = group(form, "Summary"); const summary = el("div", "sd-summary", "Checking cabinet…"); summaryGroup.append(summary);
    const syncVisibility = () => {
      frameField.hidden = style.value !== "open"; handleField.hidden = handles.value !== "true";
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
        const label = input(row.label_text); label.maxLength = 80; label.disabled = disabled;
        label.addEventListener("input", () => { row.label_text = label.value; }, { signal: events.signal });
        const labelField = labeled("Label text", label); labelField.hidden = drawerEnabled.value !== "true";
        line.append(labeled("Usable height mm", height), labelField); drawerRows.append(line);
      });
    };
    const draft = () => {
      const next = copy(space), b = next.storage_drawers;
      next.name = name.value.trim(); next.x = Number(x.value) * baseUnit; next.y = Number(y.value) * baseUnit;
      b.drawers = copy(block.drawers); b.cabinet_style = style.value; b.rear_support = rear.value;
      b.open_frame_width_mm = Number(frame.value); b.drawer_fit_mm = Number(fit.value);
      b.stacking = stack.value === "true"; b.drawer_handles = handles.value === "true"; b.drawer_handle_size = handleSize.value;
      b.unit_label_enabled = unitEnabled.value === "true"; b.unit_label_text = unitText.value;
      b.drawer_labels_enabled = drawerEnabled.value === "true"; b.drawer_label_style = labelStyle.value;
      for (const [key, control] of Object.entries(materialFields)) b[key] = Number(control.value);
      next.z = b.drawers.reduce((sum, row) => sum + row.height_mm, 0); return next;
    };
    const readFields = () => {
      const fail = (message, focusId) => ({ ok: false, message, focusId });
      if (!name.value.trim()) return fail("Enter a Space name", name.id);
      for (const [field, axis] of [[x, "X"], [y, "Y"]]) {
        const units = Number(field.value);
        if (!Number.isInteger(units) || units < 6 || units > 250) return fail(`${axis} must be 6–250 whole units`, field.id);
      }
      if (!Number.isInteger(Number(count.value)) || Number(count.value) < 1 || Number(count.value) > 32) return fail("Number of drawers must be 1–32", count.id);
      for (let i = 0; i < block.drawers.length; i++) {
        const height = block.drawers[i].height_mm;
        if (!Number.isFinite(height) || height < minDrawerHeight) return fail(`Drawer ${i + 1} needs at least ${minDrawerHeight} mm usable height`, `sd-height-${epoch}-${i}`);
      }
      if (unitEnabled.value === "true" && !unitText.value.trim()) return fail("Enter unit label text", unitText.id);
      return { ok: true, spaceDraft: draft() };
    };
    const read = () => {
      const fields = readFields();
      if (!fields.ok) return fields;
      if (summaryState === "pending") return { ok: false, message: "Checking cabinet…", focusId: null };
      if (summaryState === "error") return { ok: false, message: summaryError, focusId: null };
      if (summaryIdentity !== (callbacks.identity?.() ?? space.id ?? space.name) ||
          summaryKey !== window.StorageDrawers.structuralDraftKey(fields.spaceDraft, printerProfile)) {
        return { ok: false, message: "Checking cabinet…", focusId: null };
      }
      return fields;
    };
    const showSummary = response => {
      const outside = response.outside_xyz || [];
      const units = response.field_units || [];
      const field = response.field_mm || [];
      const heights = (response.drawers || []).map(row => row.height_mm).join(", ");
      const fitText = response.fits_printer ? "Fits printer" : (response.first_fit_error || "Does not fit printer");
      summary.textContent = `${units.join(" × ")} units (${field.join(" × ")} mm) · ${response.drawer_count} drawers (${heights} mm) · Outside ${outside.join(" × ")} mm · Printer ${printerProfile.x_mm} × ${printerProfile.y_mm} × ${printerProfile.z_mm} mm · ${fitText}`;
      if (response.warnings?.length) summary.textContent += ` · ${response.warnings.join("; ")}`;
    };
    const schedule = () => {
      summaryState = "pending"; summaryError = ""; summaryKey = null; summaryIdentity = null; summary.textContent = "Checking cabinet…";
      clearTimeout(timer); const n = ++requestNumber; const identity = callbacks.identity?.() ?? space.id ?? space.name;
      const pEpoch = profileEpoch; const checked = readFields();
      if (!checked.ok) { summaryState = "error"; summaryError = checked.message; summary.textContent = checked.message; return; }
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
          showSummary(response); summaryKey = key; summaryIdentity = identity; summaryState = "ok";
        } catch (error) {
          if (live && epoch === mountSerial && n === requestNumber && pEpoch === profileEpoch && identity === (callbacks.identity?.() ?? space.id ?? space.name) && key === window.StorageDrawers.structuralDraftKey(draft(), printerProfile)) {
            summaryError = error.message || "Cabinet is invalid"; summary.textContent = summaryError; summaryState = "error";
          }
        }
      }, 250);
    };
    count.addEventListener("change", () => {
      const wanted = Number(count.value);
      if (!Number.isInteger(wanted) || wanted < 1 || wanted > 32) { count.value = block.drawers.length; return; }
      while (block.drawers.length > wanted) tail.unshift(block.drawers.pop());
      while (block.drawers.length < wanted) block.drawers.push(tail.shift() || { temp_key: `temporary:${crypto.randomUUID()}`, height_mm: block.drawers.at(-1)?.height_mm || 40, label_text: "" });
      renderRows(); schedule();
    }, { signal: events.signal });
    form.addEventListener("input", event => { if (event.target !== count) schedule(); }, { signal: events.signal });
    form.addEventListener("change", event => {
      if (event.target !== count) { syncVisibility(); renderRows(); schedule(); }
    }, { signal: events.signal });
    syncVisibility(); renderRows(); schedule();
    return {
      read,
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
