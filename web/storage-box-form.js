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
 *        setError(), setInterior(axis, mm), getInterior() }
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
  function defaults(catalog, fieldWidth) {
    const rules = catalog?.b4b_rules || {};
    return {
      secure_lid: true, latch_count: fieldWidth > 96 ? "2" : "1", hinge_count: "2", hinge_type: "screw", lid_headroom_mm: 1, latch_tightness: "default",
      edge_bevel: "default",
      label_enabled: false, label_text: "", label_location: "top", front_label_style: "flat", label_size: "default",
      stacking: false, grid_stacking: false, handle: false,
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
    // Story 2975: a Gridfinity Storage Box Space sizes X/Y in whole cells of its
    // own pitch (read-only here: the grid and floor are fixed at creation).
    // A Wavefinity Space and every standalone design keep the 7 mm unit.
    const gridKey = initialSpace?.grid && initialSpace.grid !== "wavefinity" ? initialSpace.grid : "wavefinity";
    const baseUnit = Number(catalog?.base_unit || 7);
    const gridRow = (catalog?.grids || []).find(row => row.value === gridKey);
    const unit = gridKey === "wavefinity" ? baseUnit : (Number(gridRow?.pitch_mm) || ({ gridfinity_half: 21, gridfinity: 42 })[gridKey] || baseUnit);
    const unitName = gridKey === "wavefinity" ? "units" : "cells";
    const maxMM = 2000; // Container authority; never the single-bin ceiling.
    const minField = gridKey === "wavefinity" ? (Number(rules.min_field_mm) || unit) : unit;
    const minHeight = Number(rules.min_secure_height_mm) || 1;
    const box = { ...defaults(catalog, normalizeAxis("x", initialSpace?.x)), ...(initialSpace?.storage_box || {}), edge_bevel: bevelOf(initialSpace) };

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
    if (gridKey !== "wavefinity") {
      // Read-only: seeded from the Space record, fixed at creation. The nominal
      // grid is what the layout promises; with no floor, the printed cavity is
      // larger by the plate clearance, so the two are told apart.
      const external = (initialSpace?.built_in_grid ?? initialSpace?.storage_box?.built_in_grid ?? "floor") === "none";
      const physical = Array.isArray(initialSpace?.physical_cavity_mm) ? initialSpace.physical_cavity_mm : null;
      const gridLine = el("p", "dl-note", `${gridRow?.label || gridKey} — ${external ? "no floor (plain cavity for your own baseplate)" : "floor with raised socket grid"}. `
        + `Nominal grid ${initialSpace?.x ?? ""} × ${initialSpace?.y ?? ""} mm`
        + (external && physical ? `; printed cavity ${physical.map(n => Number(n).toFixed(1).replace(/\.0$/, "")).join(" × ")} mm` : "")
        + ". Grid and floor are set when the Space is created and cannot be changed.");
      sizeGroup.append(gridLine);
    }
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
      // X is the interior child-bin field, normalized exactly as read().
      const width = normalizeAxis("x", xInput.value);
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
      if (!latchCount.value) latchCount.value = canFitTwo ? "2" : "1";
    }
    syncLatchChoices(box.latch_count || "1");
    for (const eventName of ["input", "change"]) {
      xInput.addEventListener(eventName, () => syncLatchChoices(), { signal: events.signal });
    }
    const LATCH_TIGHTNESS = ["loose", "default", "tight"];
    const tightnessOf = value => (LATCH_TIGHTNESS.includes(value) ? value : "default");
    const latchTightness = select([["loose", "Loose"], ["default", "Default"], ["tight", "Tight"]],
      tightnessOf(box.latch_tightness));
    latchTightness.id = id("latch-tightness");
    const latchTightnessRow = labeled("Latch tightness", latchTightness);
    const latchRow = labeled("Number of latches", latchCount);
    const hingeCount = select([["2", "2"], ["1", "1"]], String(box.hinge_count) === "1" ? "1" : "2");
    hingeCount.id = id("hinge-count");
    const hingeRow = labeled("Number of hinges", hingeCount);
    const hingeType = select([["screw", "Screw hinges"], ["piano", "Piano hinge (filament pin)"]],
      box.hinge_type === "piano" ? "piano" : "screw");
    hingeType.id = id("hinge-type");
    const hingeTypeRow = labeled("Hinge type", hingeType);
    const snugnessRow = labeled("Lid head-room", snugness);
    lidRow.append(labeled("Lid type", lidType), snugnessRow, latchRow, latchTightnessRow, hingeTypeRow, hingeRow);
    const screwsLine = el("p", "dl-note");
    screwsLine.hidden = true;
    lidGroup.append(lidRow, screwsLine);
    caseWrap.append(lidGroup);

    // Options group
    const optGroup = el("div", "storage-box-group");
    const optRow = el("div", "space-dimension-row");
    const stacking = select([["false", "No recess"], ["true", "Add recess"]], String(!!box.stacking));
    stacking.id = id("stacking");
    const gridStacking = select([["false", "Off"], ["true", "Feet and lid receiving grid"]], String(!!box.grid_stacking));
    gridStacking.id = id("grid-stacking");
    const gridStackingRow = labeled("Gridfinity stacking", gridStacking);
    gridStackingRow.hidden = gridKey === "wavefinity" && !box.grid_stacking;
    const gridStackingNote = el("p", "dl-note");
    gridStackingNote.hidden = !box.grid_stacking;
    const handle = select([["false", "No handle"], ["true", "Add handle"]], String(!!box.handle));
    handle.id = id("handle");
    const handleRow = labeled("Carrying handle", handle);
    optRow.append(labeled("Wavefinity stacking recess", stacking), gridStackingRow, handleRow);
    optGroup.append(optRow, gridStackingNote);
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
    const labelSize = select([
      ["very_small", "Very small"], ["small", "Small"], ["medium", "Medium"], ["default", "Default"],
      ["medium_large", "Medium Large"], ["large", "Large"], ["extra_large", "Extra Large"],
    ], box.label_size || "default");
    labelSize.id = id("label-size");
    const labelSizeRow = labeled("Size", labelSize);
    const labelStyle = select([["flat", "Flat"], ["wavy", "Wavy"]], box.front_label_style || "flat");
    labelStyle.id = id("label-style");
    const labelStyleRow = labeled("Front label style", labelStyle);
    labelRow.append(labeled("Label", labelLoc), labelTextRow, labelSizeRow, labelStyleRow);
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

    // ---- Compact status last: the one general error surface ----
    const errorBox = el("p", "field-error", "");
    errorBox.hidden = true;
    errorBox.setAttribute("role", "alert");
    form.append(errorBox);

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

    // A Floor (raised socket grid) needs at least the catalog's floor build.
    function floorBase(chosen, stackingOn) {
      if (gridKey === "wavefinity") return chosen;
      if ((initialSpace?.built_in_grid ?? initialSpace?.storage_box?.built_in_grid ?? "floor") !== "floor") return chosen;
      const minimum = Number(stackingOn ? gridRow?.container_floor_stacking_build_mm : gridRow?.container_floor_build_mm);
      return Number.isFinite(minimum) && minimum > chosen ? minimum : chosen;
    }

    // ---- Interior sizing: the one normalization path ----
    function parseLeadingNumber(value) {
      const match = String(value ?? "").trim().match(/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/);
      return match ? Number(match[0]) : NaN;
    }
    const sizeNotes = new Map();
    function normalizeAxis(axis, requested) {
      const value = typeof requested === "number" ? requested : parseLeadingNumber(requested);
      if (!Number.isFinite(value)) return NaN;
      if (axis === "z") return Math.round(value);
      // Nearest whole cells at the pitch, never fewer than the minimum field needs.
      return gridKey === "wavefinity"
        ? Math.round(value / unit) * unit
        : Math.max(Math.ceil(minField / unit - 1e-9), Math.floor(value / unit + 0.5), 1) * unit;
    }
    function displayAxis(axis, input) {
      const raw = input.value.trim() ? Number(input.value) : NaN;
      const used = normalizeAxis(axis, raw);
      const minimum = axis === "z" ? minHeight : minField;
      const bad = !Number.isFinite(raw) || raw <= 0 || used < minimum || raw > maxMM || used > maxMM;
      const notes = [`At least ${minimum} mm and at most ${maxMM} mm.`];
      if (Number.isFinite(used) && Math.abs(raw - used) > 1e-6) notes.push(`Uses ${used} mm${axis === "z" ? "" : ` (${used / unit} ${unitName})`}.`);
      let note = sizeNotes.get(axis);
      if (!note) {
        note = el("small", "field-help"); note.id = `${input.id}-note`; note.setAttribute("aria-live", "polite");
        input.after(note); input.setAttribute("aria-describedby", note.id); sizeNotes.set(axis, note);
      }
      note.textContent = notes.join(" "); note.classList.toggle("status-error", bad);
      input.toggleAttribute("aria-invalid", bad);
      return bad ? { ok: false, message: notes[0], focusId: input.id } : { ok: true };
    }
    const inputFor = axis => (axis === "x" ? xInput : axis === "y" ? yInput : zInput);
    function getInterior() {
      return {
        x: normalizeAxis("x", xInput.value.trim() ? Number(xInput.value) : NaN),
        y: normalizeAxis("y", yInput.value.trim() ? Number(yInput.value) : NaN),
        z: normalizeAxis("z", zInput.value.trim() ? Number(zInput.value) : NaN),
      };
    }
    // Typed input, arrow/wheel steps and the 3D handles all land here.
    function setInterior(axis, requested, { silent = false } = {}) {
      const input = inputFor(axis);
      input.value = String(requested);
      const value = normalizeAxis(axis, requested);
      displayAxis(axis, input);
      if (axis === "x") syncLatchChoices();
      if (!silent) onChange();
      return value;
    }
    for (const axis of ["x", "y", "z"]) {
      const input = inputFor(axis);
      input.addEventListener("blur", () => displayAxis(axis, input), { signal: events.signal });
      input.addEventListener("change", onChange, { signal: events.signal });
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
      const gridOn = gridStacking.value === "true";
      const topOption = labelLoc.querySelector('option[value="top"]');
      topOption.hidden = gridOn;
      topOption.disabled = gridOn;
      gridStackingNote.hidden = !gridOn;
      gridStackingNote.textContent = "Fit, closure and mating are unverified. Remove the upper box before opening the lid. The lid keeps its flipped print pose, resting on the ridge crest.";
      latchRow.hidden = !latched;
      latchTightnessRow.hidden = !latched;
      hingeTypeRow.hidden = !latched;
      // a piano hinge runs the full width, so there is no count to choose
      hingeRow.hidden = !latched || hingeType.value === "piano";
      snugnessRow.hidden = !latched;
      handleRow.hidden = !latched;
      if (!latched) handle.value = "false";
      const labeledOn = labelLoc.value !== "none";
      labelTextRow.hidden = !labeledOn;
      labelSizeRow.hidden = !labeledOn;
      labelStyleRow.hidden = !(labeledOn && labelLoc.value === "front");
    }
    lidType.addEventListener("change", syncVisibility, { signal: events.signal });
    labelLoc.addEventListener("change", syncVisibility, { signal: events.signal });
    syncVisibility();

    // ---- Draft ----
    // The current form values carry normalized sizes for preview and autosave.
    function read() {
      const checks = ["x", "y", "z"].map(axis => displayAxis(axis, inputFor(axis)));
      const invalid = checks.find(check => !check.ok);
      if (invalid) return invalid;
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
      if (latched && (x < 48 || y < 48)) {
        return { ok: false, message: "A latched Storage Box needs at least 48 mm of width and depth. Use Lid only for a smaller box.", focusId: id("lid-type") };
      }
      if (gridStacking.value === "true") {
        let message = "";
        if (gridKey === "wavefinity") message = "Grid stacking needs a 21 mm or 42 mm Gridfinity Storage Box.";
        else if (stacking.value === "true") message = "Grid stacking cannot be combined with the Wavefinity stacking recess and pegs. Turn one off.";
        else if (labelLoc.value === "top") message = "Grid stacking cannot use a lid-top label. Choose Front or No label.";
        else if (latched && hingeType.value === "piano") message = "Grid stacking is unavailable with a piano hinge. Choose screw hinges or Lid only.";
        else if (latched && latchCount.value === "0") message = "Grid stacking with a latched lid needs one or two latches. Choose a latch count or Lid only.";
        if (message) return { ok: false, message, focusId: id("grid-stacking") };
      }
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
            latch_tightness: tightnessOf(latchTightness.value),
            edge_bevel: bevel.value,
            label_enabled: labelOn,
            label_text: labelOn ? labelText.value.trim() : "",
            label_location: labelOn ? labelLoc.value : (gridStacking.value === "true" ? "none" : "top"),
            front_label_style: labelStyle.value,
            label_size: labelSize.value,
            stacking: stacking.value === "true",
            grid_stacking: gridStacking.value === "true",
            handle: latched && handle.value === "true",
            wall_mm: Number(wallSel.value),
            base_mm: floorBase(Number(baseSel.value), stacking.value === "true"),
          },
        },
      };
    }

    // Dirty tracking.
    let pristine = JSON.stringify(read());
    function isDirty() { return JSON.stringify(read()) !== pristine; }
    function markPristine() { pristine = JSON.stringify(read()); }

    function onChange() {
      screwsLine.hidden = true;
      syncVisibility();
      const draft = read();
      setError(draft.ok ? "" : draft.message);
      if (callbacks.onChange) callbacks.onChange(draft);
    }
    hingeType.addEventListener("change", syncVisibility, { signal: events.signal });
    for (const input of [lidType, snugness, latchCount, hingeCount, hingeType, latchTightness, stacking, gridStacking, handle, labelLoc, labelText, labelSize, labelStyle, wallSel, baseSel, bevel]) {
      input.addEventListener("input", onChange, { signal: events.signal });
      input.addEventListener("change", onChange, { signal: events.signal });
    }
    // Typed dimensions autosave normalized values without rewriting the field.
    for (const input of [xInput, yInput, zInput]) {
      input.addEventListener("input", onChange, { signal: events.signal });
    }

    function fill(space) {
      const b = { ...defaults(catalog, normalizeAxis("x", space?.x)), ...(space?.storage_box || {}) };
      xInput.value = String(space?.x || "");
      yInput.value = String(space?.y || "");
      zInput.value = String(space?.z || "");
      for (const axis of ["x", "y", "z"]) displayAxis(axis, inputFor(axis));
      lidType.value = b.secure_lid ? "latched" : "lid_only";
      snugness.value = String(b.lid_headroom_mm ?? 1);
      latchTightness.value = tightnessOf(b.latch_tightness);
      bevel.value = bevelOf(space);
      syncLatchChoices(b.latch_count || "1");
      hingeCount.value = String(b.hinge_count) === "1" ? "1" : "2";
      hingeType.value = b.hinge_type === "piano" ? "piano" : "screw";
      stacking.value = String(!!b.stacking);
      gridStacking.value = String(!!b.grid_stacking);
      handle.value = String(!!b.handle);
      labelLoc.value = b.label_enabled ? (b.label_location || "top") : "none";
      labelText.value = b.label_text || "";
      labelStyle.value = b.front_label_style || "flat";
      labelSize.value = b.label_size || "default";
      fillMaterial(wallSel, rules.wall_choices, b.wall_mm);
      fillMaterial(baseSel, rules.base_choices, b.base_mm);
      syncVisibility();
      markPristine();
    }

    function setSummary(summary) {
      if (summary?.grid_stacking_model && gridStacking.value === "true") {
        const model = summary.grid_stacking_model;
        const reach = model.open_lid_rear_reach_mm;
        gridStackingNote.textContent = `Fit, closure and mating are unverified. Closed height with feet and grid: ${Number(model.closed_with_grid_mm).toFixed(2)} mm.`
          + (Number.isFinite(reach) ? ` Allow at least ${reach.toFixed(2)} mm behind the rear crest for the nominal open-lid envelope.` : "")
          + " Remove the upper box before opening. The lid keeps its flipped print pose, resting on the ridge crest; barrel print quality is unverified.";
      }
      const totals = summary?.screw_totals || [];
      screwsLine.textContent = totals.length
        ? `Screws needed: ${totals.map(([family, length, count]) => `${family} × ${length} mm (${count})`).join(", ")}`
        : "";
      screwsLine.hidden = !totals.length;
    }

    function setError(message) {
      errorBox.textContent = message || "";
      errorBox.hidden = !message;
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
      for (const input of [xInput, yInput, zInput, lidType, snugness, latchCount, latchTightness, stacking, gridStacking, handle, labelLoc, labelText, labelSize, labelStyle, wallSel, baseSel, bevel]) {
        input.disabled = frozen;
      }
    }

    return { read, draft: read, fill, destroy, isDirty, markPristine, setError, setSummary, setInterior, getInterior, setDisabled };
  }

  window.StorageBoxForm = { mount };
})();
