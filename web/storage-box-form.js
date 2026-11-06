/* Wavefinity — Storage Box structural editor (Fix 103, Section C).
 * Mountable full-detail form for the Storage Box case in the Design panel.
 * Mirrors the setup dialog's #space-fields-portable controls, but built in
 * JS with epoch-suffixed IDs so it can live in the Design panel without
 * colliding with the setup dialog's static IDs.
 *
 * The structural editor automatically saves changes to the Space.
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
      secure_lid: true, latch_count: "1", hinge_count: "2", hinge_type: "screw", lid_headroom_mm: 1,
      edge_bevel: "default",
      label_enabled: false, label_text: "", label_location: "top", front_label_style: "flat",
      stacking: false, handle: false,
      wall_mm: Number(rules.default_wall_mm ?? 1.6),
      base_mm: Number(rules.default_base_mm ?? 1.6),
    };
  }

  // A new design starts on Default; a saved Storage Box with no bevel value
  // predates the option and has sharp edges.
  const BEVELS = ["none", "light", "default", "heavy"];
  function bevelOf(space) {
    const saved = space?.storage_box;
    if (!saved) return "default";
    return BEVELS.includes(saved.edge_bevel) ? saved.edge_bevel : "none";
  }

  function mount({ host, initialSpace, callbacks = {} }) {
    const catalog = (typeof state !== "undefined" && state.catalog) || null;
    const rules = catalog?.b4b_rules || {};
    const unit = Number(catalog?.base_unit || 7);
    const maxXY = Math.floor(Number(catalog?.max_box_size || 350) / unit) * unit;
    const minField = Number(rules.min_field_mm) || unit;
    const minHeight = Number(rules.min_secure_height_mm) || 1;
    const box = { ...defaults(catalog), ...(initialSpace?.storage_box || {}), edge_bevel: bevelOf(initialSpace) };

    const form = el("div", "storage-box-form");   // one column of areas: size, Lid, options, Label, Material, status
    const events = new AbortController();

    // ---- Interior size (Width / Depth / Height, three across) ----
    const sizeGroup = el("div", "storage-box-group");
    const sizeRow = el("div", "space-dimension-row");
    const sizeInput = (axis, value) => {
      const input = document.createElement("input");
      input.type = "text"; input.inputMode = "numeric";
      input.id = id(axis);
      input.min = String(axis === "z" ? minHeight : minField);
      input.step = axis === "z" ? "1" : String(unit);
      input.value = value || "";
      return input;
    };
    const xInput = sizeInput("x", initialSpace?.x);
    const yInput = sizeInput("y", initialSpace?.y);
    const zInput = sizeInput("z", initialSpace?.z);
    const xLabel = labeled("Interior Width (mm)", xInput);
    const yLabel = labeled("Interior Depth (mm)", yInput);
    const zLabel = labeled("Interior Height (mm)", zInput);
    sizeRow.append(xLabel, yLabel, zLabel);
    sizeGroup.append(sizeRow);
    const outside = el("p", "storage-box-capacity");
    form.append(sizeGroup);

    // ---- Case Settings ----
    const caseWrap = el("div", "storage-box-case");

    // Lid group
    const lidGroup = el("div", "storage-box-group");
    const lidRow = el("div", "space-dimension-row");
    const lidType = select([["latched", "Latched lid"], ["lid_only", "Lid only"]],
      box.secure_lid ? "latched" : "lid_only");
    lidType.id = id("lid-type");
    const snugness = select([["0.5", "0.5 mm — Tight"], ["1", "1.0 mm — Standard"], ["2", "2.0 mm — Loose"]],
      String(box.lid_headroom_mm ?? 1));
    snugness.id = id("lid-snugness");
    const latchCount = select([], "1");
    latchCount.id = id("latch-count");
    function syncLatchChoices(preferred = latchCount.value) {
      const width = parseLeadingNumber(xInput.value);
      const canFitTwo = Number.isFinite(width) && width > 96;
      const legacyChoice = preferred === "auto"
        ? (canFitTwo ? "2" : "1")
        : preferred;
      latchCount.replaceChildren();
      for (const [value, label] of [["0", "None"], ["1", "1"], ...(canFitTwo ? [["2", "2"]] : [])]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        latchCount.append(option);
      }
      latchCount.value = legacyChoice === "2" && !canFitTwo ? "1" : legacyChoice;
      if (!latchCount.value) latchCount.value = "1";
    }
    syncLatchChoices(box.latch_count || "1");
    for (const eventName of ["input", "change"]) {
      xInput.addEventListener(eventName, () => syncLatchChoices(), { signal: events.signal });
    }
    const latchRow = labeled("Number of latches", latchCount);
    const hingeCount = select([["2", "2"], ["1", "1"]], String(box.hinge_count) === "1" ? "1" : "2");
    hingeCount.id = id("hinge-count");
    const hingeRow = labeled("Number of hinges", hingeCount);
    const hingeType = select([["screw", "Screw hinges"], ["piano", "Piano hinge (filament pin)"]],
      box.hinge_type === "piano" ? "piano" : "screw");
    hingeType.id = id("hinge-type");
    const hingeTypeRow = labeled("Hinge type", hingeType);
    const snugnessRow = labeled("Lid snugness", snugness);
    lidRow.append(labeled("Lid type", lidType), snugnessRow, latchRow, hingeTypeRow, hingeRow);
    lidGroup.append(lidRow);
    caseWrap.append(lidGroup);

    // Options group
    const optGroup = el("div", "storage-box-group");
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
    labelRow.append(labeled("Label", labelLoc), labelTextRow, labelStyleRow);
    labelGroup.append(labelRow);
    caseWrap.append(labelGroup);

    // Material group
    const matGroup = el("div", "storage-box-group");
    const matRow = el("div", "space-dimension-row");
    const wallSel = document.createElement("select"); wallSel.id = id("wall");
    const baseSel = document.createElement("select"); baseSel.id = id("base");
    const bevel = select([["none", "No bevel"], ["light", "Light"], ["default", "Default"], ["heavy", "Heavy"]],
      box.edge_bevel);
    bevel.id = id("edge-bevel");
    matRow.append(labeled("Wall thickness", wallSel), labeled("Base/Lid thickness", baseSel),
      labeled("Edge bevel", bevel));
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
    function parseLeadingNumber(value) {
      const match = String(value ?? "").trim().match(/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/);
      return match ? Number(match[0]) : NaN;
    }
    function formatAxis(axis, value) {
      if (!(value > 0)) return "";
      if (axis === "z") return `${value} mm`;
      const units = Math.round(value / unit);
      return `${value} (${units} unit${units === 1 ? "" : "s"})`;
    }
    function displayAxis(axis, input) {
      const value = parseLeadingNumber(input.value);
      if (!Number.isFinite(value)) return;
      input.value = document.activeElement === input ? String(value) : formatAxis(axis, value);
    }
    function normalizeAxis(axis, requested, fallback) {
      const parsed = typeof requested === "number" ? requested : parseLeadingNumber(requested);
      const fallbackValue = typeof fallback === "number" ? fallback : parseLeadingNumber(fallback);
      const value = Number.isFinite(parsed) ? parsed : fallbackValue;
      if (!Number.isFinite(value)) return NaN;
      if (axis === "z") return Math.max(minHeight, Math.round(value));
      return Math.min(maxXY, Math.max(minField, Math.round(value / unit) * unit));
    }
    const inputFor = axis => (axis === "x" ? xInput : axis === "y" ? yInput : zInput);
    function getInterior() {
      return {
        x: normalizeAxis("x", parseLeadingNumber(xInput.value), NaN),
        y: normalizeAxis("y", parseLeadingNumber(yInput.value), NaN),
        z: normalizeAxis("z", parseLeadingNumber(zInput.value), NaN),
      };
    }
    // Typed input, arrow/wheel steps and the 3D handles all land here.
    function setInterior(axis, requested, { silent = false } = {}) {
      const input = inputFor(axis);
      const value = normalizeAxis(axis, requested, input.value);
      if (!Number.isFinite(value)) return NaN;
      input.value = document.activeElement === input ? String(value) : formatAxis(axis, value);
      if (axis === "x") syncLatchChoices();
      if (!silent) onChange();
      return value;
    }
    for (const axis of ["x", "y", "z"]) {
      const input = inputFor(axis);
      input.addEventListener("focus", () => displayAxis(axis, input), { signal: events.signal });
      input.addEventListener("blur", () => {
        setInterior(axis, parseLeadingNumber(input.value));
        displayAxis(axis, input);
      }, { signal: events.signal });
      input.addEventListener("change", () => setInterior(axis, parseLeadingNumber(input.value)), { signal: events.signal });
      input.addEventListener("keydown", event => {
        if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
        event.preventDefault();
        const step = axis === "z" ? 1 : unit;
        setInterior(axis, parseLeadingNumber(input.value || 0) + (event.key === "ArrowUp" ? step : -step));
      }, { signal: events.signal });
      input.addEventListener("wheel", event => {
        if (document.activeElement !== input) return;
        event.preventDefault();
        const step = axis === "z" ? 1 : unit;
        setInterior(axis, parseLeadingNumber(input.value || 0) + (event.deltaY < 0 ? step : -step));
      }, { signal: events.signal, passive: false });
    }
    for (const axis of ["x", "y", "z"]) displayAxis(axis, inputFor(axis));

    // Visibility: latch/snugness only for latched; label text/style only when labeled.
    function syncVisibility() {
      const latched = lidType.value === "latched";
      latchRow.hidden = !latched;
      hingeTypeRow.hidden = !latched;
      // a piano hinge runs the full width, so there is no count to choose
      hingeRow.hidden = !latched || hingeType.value === "piano";
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
    // The current form values carry normalized sizes for preview and autosave.
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
            latch_count: latchCount.value,
            hinge_count: latched ? hingeCount.value : "2",
            hinge_type: latched ? hingeType.value : "screw",
            lid_headroom_mm: latched ? Number(snugness.value) : 1,
            edge_bevel: bevel.value,
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
    hingeType.addEventListener("change", syncVisibility, { signal: events.signal });
    for (const input of [lidType, snugness, latchCount, hingeCount, hingeType, stacking, handle, labelLoc, labelText, labelStyle, wallSel, baseSel, bevel]) {
      input.addEventListener("input", onChange, { signal: events.signal });
      input.addEventListener("change", onChange, { signal: events.signal });
    }
    // Typed dimensions autosave normalized values without rewriting the field.
    for (const input of [xInput, yInput, zInput]) {
      input.addEventListener("input", onChange, { signal: events.signal });
    }

    function fill(space) {
      const b = { ...defaults(catalog), ...(space?.storage_box || {}) };
      xInput.value = String(space?.x || "");
      yInput.value = String(space?.y || "");
      zInput.value = String(space?.z || "");
      for (const axis of ["x", "y", "z"]) displayAxis(axis, inputFor(axis));
      lidType.value = b.secure_lid ? "latched" : "lid_only";
      snugness.value = String(b.lid_headroom_mm ?? 1);
      bevel.value = bevelOf(space);
      syncLatchChoices(b.latch_count || "1");
      hingeCount.value = String(b.hinge_count) === "1" ? "1" : "2";
      hingeType.value = b.hinge_type === "piano" ? "piano" : "screw";
      stacking.value = String(!!b.stacking);
      handle.value = String(!!b.handle);
      labelLoc.value = b.label_enabled ? (b.label_location || "top") : "none";
      labelText.value = b.label_text || "";
      labelStyle.value = b.front_label_style || "flat";
      fillMaterial(wallSel, rules.wall_choices, b.wall_mm);
      fillMaterial(baseSel, rules.base_choices, b.base_mm);
      syncVisibility();
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

    // Fix 1104 (Astra AD-003): freeze every field while a structural save is in
    // flight, mirroring StorageDrawersForm's setDisabled. Disabled fields can
    // neither be typed in nor arrow/wheel-stepped, so the save's draft snapshot
    // cannot be silently superseded by newer input.
    function setDisabled(value) {
      const frozen = !!value;
      for (const input of [xInput, yInput, zInput, lidType, snugness, latchCount, stacking, handle, labelLoc, labelText, labelStyle, wallSel, baseSel, bevel]) {
        input.disabled = frozen;
      }
    }

    return { read, draft: read, fill, destroy, isDirty, markPristine, setError, setInterior, getInterior, setOutside, setDisabled };
  }

  window.StorageBoxForm = { mount };
})();
