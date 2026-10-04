/* Wavefinity — Storage Box structural editor (Fix 103, Section C).
 * Mountable full-detail form for the Storage Box case in the Design panel.
 * Mirrors the setup dialog's #space-fields-portable controls, but built in
 * JS with epoch-suffixed IDs so it can live in the Design panel without
 * colliding with the setup dialog's static IDs.
 *
 * The form owns the unsaved draft (Fix 103 R2). It never persists anything:
 * Save Changes lives in the structural editor controller.
 *
 * API: window.StorageBoxForm.mount({ host, initialSpace, callbacks })
 *   -> { read(), draft(), fill(space), destroy(), isDirty(), markPristine(),
 *        setError(), setInterior(axis, mm), getInterior(), setOutside(mm) }
 *
 * Interior sizing (Fix 103 R1): Width/Depth are whole catalog base units (shown in mm);
 * Height is a whole mm at or above the legal minimum and is never snapped to
 * the X/Y grid. Typed input, arrow/wheel steps and the 3D handles all go
 * through setInterior().
 */
(function () {
  "use strict";

  const epoch = (typeof crypto !== "undefined" && crypto.randomUUID)
    ? crypto.randomUUID().slice(0, 8)
    : String(Date.now() % 100000);

  const id = name => `sbf-${name}-${epoch}`;

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function labeled(labelText, control) {
    const label = el("label", "space-field");
    label.append(el("span", null, labelText), control);
    return label;
  }

  function select(options, value) {
    const sel = document.createElement("select");
    for (const [val, label] of options) {
      const opt = document.createElement("option");
      opt.value = val; opt.textContent = label;
      sel.append(opt);
    }
    sel.value = value;
    return sel;
  }

  // Canonical defaults — MUST match SP.storageBoxDefaults() in spaces.js.
  // If that function changes, this must change identically.
  function defaults(catalog) {
    const rules = catalog?.b4b_rules || {};
    return {
      secure_lid: true, latch_count: "auto", lid_headroom_mm: 1,
      label_enabled: false, label_text: "", label_location: "top", front_label_style: "flat",
      stacking: false, handle: false,
      wall_mm: Number(rules.default_wall_mm ?? 1.6),
      base_mm: Number(rules.default_base_mm ?? 1.6),
    };
  }

  function mount({ host, initialSpace, callbacks = {} }) {
    const catalog = (typeof state !== "undefined" && state.catalog) || null;
    const rules = catalog?.b4b_rules || {};
    const unit = Number(catalog?.base_unit || 8);
    const maxXY = Math.floor(Number(catalog?.max_box_size || 350) / unit) * unit;
    const minField = Number(rules.min_field_mm) || unit;
    const minHeight = Number(rules.min_secure_height_mm) || 1;
    const box = { ...defaults(catalog), ...(initialSpace?.storage_box || {}) };

    const form = el("div", "storage-box-form");   // one column of areas: size, Lid, Case Options, Label, Material, status
    const events = new AbortController();

    // ---- Interior size (Width / Depth / Height, three across) ----
    const sizeGroup = el("div", "storage-box-group");
    sizeGroup.append(el("h5", "storage-box-subtitle", "Interior size"));
    const sizeRow = el("div", "space-dimension-row");
    const sizeInput = (axis, value) => {
      const input = document.createElement("input");
      input.type = "number"; input.inputMode = "decimal";
      input.id = id(axis);
      input.min = String(axis === "z" ? minHeight : minField);
      input.step = axis === "z" ? "1" : String(unit);
      input.value = value || "";
      return input;
    };
    const xInput = sizeInput("x", initialSpace?.x);
    const yInput = sizeInput("y", initialSpace?.y);
    const zInput = sizeInput("z", initialSpace?.z);
    const xUnits = el("small", "storage-box-units"), yUnits = el("small", "storage-box-units");
    const zNote = el("small", "storage-box-units");
    const xLabel = labeled("Interior Width (mm)", xInput); xLabel.append(xUnits);
    const yLabel = labeled("Interior Depth (mm)", yInput); yLabel.append(yUnits);
    const zLabel = labeled("Interior Height (mm)", zInput); zLabel.append(zNote);
    sizeRow.append(xLabel, yLabel, zLabel);
    sizeGroup.append(sizeRow);
    const outside = el("p", "storage-box-capacity");
    form.append(sizeGroup);

    // ---- Case Settings ----
    const caseWrap = el("div", "storage-box-case");
    caseWrap.append(el("h4", "storage-box-title", "Case Settings"));

    // Lid group
    const lidGroup = el("div", "storage-box-group");
    lidGroup.append(el("h5", "storage-box-subtitle", "Lid"));
    const lidRow = el("div", "space-dimension-row");
    const lidType = select([["latched", "Latched lid"], ["lid_only", "Lid only"]],
      box.secure_lid ? "latched" : "lid_only");
    lidType.id = id("lid-type");
    const snugness = select([["0.5", "0.5 mm — Tight"], ["1", "1.0 mm — Standard"], ["2", "2.0 mm — Loose"]],
      String(box.lid_headroom_mm ?? 1));
    snugness.id = id("lid-snugness");
    const latchCount = select([["auto", "Auto"], ["1", "1"], ["2", "2"]], box.latch_count || "auto");
    latchCount.id = id("latch-count");
    const latchRow = labeled("# of latches", latchCount);
    const snugnessRow = labeled("Lid snugness", snugness);
    lidRow.append(labeled("Lid type", lidType), snugnessRow, latchRow);
    lidGroup.append(lidRow);
    caseWrap.append(lidGroup);

    // Options group
    const optGroup = el("div", "storage-box-group");
    optGroup.append(el("h5", "storage-box-subtitle", "Case Options"));
    const optRow = el("div", "space-dimension-row");
    const stacking = select([["false", "Not stackable"], ["true", "Stackable"]], String(!!box.stacking));
    stacking.id = id("stacking");
    const handle = select([["false", "No handle"], ["true", "Add handle"]], String(!!box.handle));
    handle.id = id("handle");
    const handleRow = labeled("Carrying handle", handle);
    optRow.append(labeled("Case stacking", stacking), handleRow);
    optGroup.append(optRow);
    caseWrap.append(optGroup);

    // Label group
    const labelGroup = el("div", "storage-box-group");
    labelGroup.append(el("h5", "storage-box-subtitle", "Label"));
    const labelRow = el("div", "space-dimension-row");
    const labelLoc = select([["none", "No label"], ["top", "Top"], ["front", "Front"]],
      box.label_enabled ? (box.label_location || "top") : "none");
    labelLoc.id = id("label-location");
    const labelText = document.createElement("input");
    labelText.type = "text"; labelText.maxLength = 80;
    labelText.placeholder = "e.g. M3 HARDWARE";
    labelText.id = id("label-text"); labelText.value = box.label_text || "";
    const labelTextRow = labeled("Label text", labelText);
    const labelStyle = select([["flat", "Flat"], ["wavy", "Wavy"]], box.front_label_style || "flat");
    labelStyle.id = id("label-style");
    const labelStyleRow = labeled("Front label style", labelStyle);
    labelRow.append(labeled("Location", labelLoc), labelTextRow, labelStyleRow);
    labelGroup.append(labelRow);
    caseWrap.append(labelGroup);

    // Material group
    const matGroup = el("div", "storage-box-group");
    matGroup.append(el("h5", "storage-box-subtitle", "Material"));
    const matRow = el("div", "space-dimension-row");
    const wallSel = document.createElement("select"); wallSel.id = id("wall");
    const baseSel = document.createElement("select"); baseSel.id = id("base");
    matRow.append(labeled("Wall thickness", wallSel), labeled("Base thickness", baseSel));
    matGroup.append(matRow);
    caseWrap.append(matGroup);

    form.append(caseWrap);

    // ---- Compact status last: finished-outside result, then the one general error surface ----
    const errorBox = el("p", "field-error", "");
    errorBox.hidden = true;
    errorBox.setAttribute("role", "alert");
    form.append(outside, errorBox);

    host.append(form);

    // Populate material selects from catalog.
    function fillMaterial(selectEl, choices, value) {
      const rows = (choices || []).map(one => ({ value: Number(one.value), label: one.label }));
      if (!rows.some(one => Math.abs(one.value - value) < 1e-9)) rows.push({ value, label: "Custom" });
      selectEl.innerHTML = rows.map(one =>
        `<option value="${one.value}">${one.value} mm — ${one.label.replace(/</g, "&lt;")}</option>`).join("");
      selectEl.value = String(value);
    }
    fillMaterial(wallSel, rules.wall_choices, box.wall_mm);
    fillMaterial(baseSel, rules.base_choices, box.base_mm);

    // ---- Interior sizing: the one normalization path ----
    function normalizeAxis(axis, requested, fallback) {
      const value = Number.isFinite(Number(requested)) && String(requested).trim() !== ""
        ? Number(requested) : Number(fallback);
      if (!Number.isFinite(value)) return NaN;
      if (axis === "z") return Math.max(minHeight, Math.round(value));
      return Math.min(maxXY, Math.max(minField, Math.round(value / unit) * unit));
    }
    const inputFor = axis => (axis === "x" ? xInput : axis === "y" ? yInput : zInput);
    // mm-only grid note: quiet when the typed value is already on the grid,
    // otherwise the mm size that will be committed. Never rewrites the field.
    function gridNote(axis) {
      const raw = Number(inputFor(axis).value);
      if (!(raw > 0)) return "";
      const mm = normalizeAxis(axis, raw, raw);
      return raw === mm ? `${unit} mm grid` : `Will save as ${mm} mm · ${unit} mm grid`;
    }
    function showReadouts() {
      xUnits.textContent = gridNote("x");
      yUnits.textContent = gridNote("y");
      zNote.textContent = Number(zInput.value) > 0 ? "whole mm" : "";
    }
    function getInterior() {
      return {
        x: normalizeAxis("x", xInput.value, NaN),
        y: normalizeAxis("y", yInput.value, NaN),
        z: normalizeAxis("z", zInput.value, NaN),
      };
    }
    // Typed input, arrow/wheel steps and the 3D handles all land here.
    function setInterior(axis, requested, { silent = false } = {}) {
      const input = inputFor(axis);
      const value = normalizeAxis(axis, requested, input.value);
      if (!Number.isFinite(value)) return NaN;
      input.value = String(value);
      showReadouts();
      if (!silent) onChange();
      return value;
    }
    for (const axis of ["x", "y", "z"]) {
      const input = inputFor(axis);
      input.addEventListener("change", () => setInterior(axis, input.value), { signal: events.signal });
      input.addEventListener("keydown", event => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault();
        const step = axis === "z" ? 1 : unit;
        setInterior(axis, Number(input.value || 0) + (event.key === "ArrowUp" ? step : -step));
      }, { signal: events.signal });
      input.addEventListener("wheel", event => {
        if (document.activeElement !== input) return;
        event.preventDefault();
        const step = axis === "z" ? 1 : unit;
        setInterior(axis, Number(input.value || 0) + (event.deltaY < 0 ? step : -step));
      }, { signal: events.signal, passive: false });
    }
    showReadouts();

    // Visibility: latch/snugness only for latched; label text/style only when labeled.
    function syncVisibility() {
      const latched = lidType.value === "latched";
      latchRow.hidden = !latched;
      snugnessRow.hidden = !latched;
      handleRow.hidden = !latched;
      if (!latched) handle.value = "false";
      const labeledOn = labelLoc.value !== "none";
      labelTextRow.hidden = !labeledOn;
      labelStyleRow.hidden = !(labeledOn && labelLoc.value === "front");
    }
    lidType.addEventListener("change", syncVisibility, { signal: events.signal });
    labelLoc.addEventListener("change", syncVisibility, { signal: events.signal });
    syncVisibility();

    // ---- Draft ----
    // The draft always carries normalized sizes; it is what the provisional
    // preview and Save Changes both consume.
    function read() {
      const { x, y, z } = getInterior();
      if (!(x > 0 && y > 0 && z > 0)) {
        return { ok: false, message: "Enter a width, depth, and height greater than zero.", focusId: id("x") };
      }
      if (x < minField || y < minField) {
        return { ok: false, message: `A Storage Box needs at least ${minField} × ${minField} mm of interior width and depth.`, focusId: id("x") };
      }
      if (z < minHeight) {
        return { ok: false, message: `A Storage Box's interior height must be at least ${minHeight} mm.`, focusId: id("z") };
      }
      const latched = lidType.value === "latched";
      const labelOn = labelLoc.value !== "none";
      return {
        ok: true,
        space: {
          x, y, z,
          storage_box: {
            secure_lid: latched,
            latch_count: latched ? latchCount.value : "auto",
            lid_headroom_mm: latched ? Number(snugness.value) : 1,
            label_enabled: labelOn,
            label_text: labelOn ? labelText.value.trim() : "",
            label_location: labelOn ? labelLoc.value : "top",
            front_label_style: labelStyle.value,
            stacking: stacking.value === "true",
            handle: latched && handle.value === "true",
            wall_mm: Number(wallSel.value),
            base_mm: Number(baseSel.value),
          },
        },
      };
    }

    // Dirty tracking.
    let pristine = JSON.stringify(read());
    function isDirty() { return JSON.stringify(read()) !== pristine; }
    function markPristine() { pristine = JSON.stringify(read()); }

    function onChange() {
      if (callbacks.onChange) callbacks.onChange(read());
    }
    for (const input of [lidType, snugness, latchCount, stacking, handle, labelLoc, labelText, labelStyle, wallSel, baseSel]) {
      input.addEventListener("input", onChange, { signal: events.signal });
      input.addEventListener("change", onChange, { signal: events.signal });
    }
    // Width/Depth/Height raise onChange from setInterior (after normalizing);
    // a raw "input" event alone only keeps the unit readout honest.
    for (const input of [xInput, yInput, zInput]) {
      input.addEventListener("input", showReadouts, { signal: events.signal });
    }

    function fill(space) {
      const b = { ...defaults(catalog), ...(space?.storage_box || {}) };
      xInput.value = space?.x || "";
      yInput.value = space?.y || "";
      zInput.value = space?.z || "";
      lidType.value = b.secure_lid ? "latched" : "lid_only";
      snugness.value = String(b.lid_headroom_mm ?? 1);
      latchCount.value = b.latch_count || "auto";
      stacking.value = String(!!b.stacking);
      handle.value = String(!!b.handle);
      labelLoc.value = b.label_enabled ? (b.label_location || "top") : "none";
      labelText.value = b.label_text || "";
      labelStyle.value = b.front_label_style || "flat";
      fillMaterial(wallSel, rules.wall_choices, b.wall_mm);
      fillMaterial(baseSel, rules.base_choices, b.base_mm);
      syncVisibility();
      showReadouts();
      markPristine();
    }

    function setError(message) {
      errorBox.textContent = message || "";
      errorBox.hidden = !message;
    }

    // The server-derived finished outside size (never computed here).
    function setOutside(sizeMm) {
      outside.textContent = Array.isArray(sizeMm) && sizeMm.length >= 3
        ? `Finished outside ${sizeMm.map(value => String(Math.round(Number(value) * 10) / 10)).join(" × ")} mm`
        : "";
    }

    function destroy() {
      events.abort();
      form.remove();
    }

    return { read, draft: read, fill, destroy, isDirty, markPristine, setError, setInterior, getInterior, setOutside };
  }

  window.StorageBoxForm = { mount };
})();
