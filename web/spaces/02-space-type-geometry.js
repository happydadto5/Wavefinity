"use strict";

// The single source of the Small/Medium/Large Surface trim presets: the
// authoritative Base Trim catalog, never a second hard-coded mm table.
SP.surfacePresetRows = () => {
  const rows = state.catalog?.base_trim_rules?.size_presets || [];
  return rows.filter(row => ["small", "medium", "large"].includes(row.key));
};

SP.surfacePresetMap = () => Object.fromEntries(
  SP.surfacePresetRows().map(row => [row.key, Number(row.value_mm)])
);

SP.surfaceTrimKeyForHeight = value => {
  const z = Number(value);
  if (!Number.isFinite(z)) return null;
  for (const [key, height] of Object.entries(SP.surfacePresetMap())) {
    if (Math.abs(z - height) <= 1e-6) return key;
  }
  return null;
};

// Surface setup asks for the maximum finished OUTSIDE size in mm. Space
// x / y stay the interior Wavefinity field in mm; this is the one place that
// converts between the two, using the catalog's Base Trim rules (never a
// second hard-coded table):
//   outside = field + mating gap + 2 * trim width
SP.surfaceRules = () => {
  const rules = state.catalog?.base_trim_rules || {};
  return {
    unit: Number(rules.unit_mm || state.catalog?.base_unit),
    gap: Number(rules.mating_gap_mm),
    maxField: Number(rules.max_field_mm),
  };
};

SP.surfaceOutsideFor = (fieldMm, trimKey) => {
  const { gap } = SP.surfaceRules();
  const width = SP.surfacePresetMap()[trimKey];
  return fieldMm + gap + 2 * width;
};

// Largest whole-unit interior field that fits inside the requested outside
// size (never nearest/up). Returns { ok, error, fieldX, fieldY, unitsX,
// unitsY, outerX, outerY, trimWidth }.
SP.resolveSurface = (requestedX, requestedY, trimKey) => {
  const { unit, gap, maxField } = SP.surfaceRules();
  const width = SP.surfacePresetMap()[trimKey];
  if (!Number.isFinite(width)) return { ok: false, error: "Choose Small, Medium, or Large trim." };
  if (!Number.isFinite(requestedX) || !Number.isFinite(requestedY) || requestedX <= 0 || requestedY <= 0) {
    return { ok: false, error: "Enter the outside width and length in mm." };
  }
  const epsilon = 1e-6;
  const extra = gap + 2 * width;
  const unitsFor = requested => Math.floor((requested - extra + epsilon) / unit);
  const unitsX = unitsFor(requestedX);
  const unitsY = unitsFor(requestedY);
  if (unitsX < 1 || unitsY < 1) {
    return {
      ok: false,
      error: `Too small: the smallest Surface is ${fmt(unit + extra)} mm outside with this trim.`,
    };
  }
  const fieldX = unitsX * unit;
  const fieldY = unitsY * unit;
  if (fieldX > maxField + epsilon || fieldY > maxField + epsilon) {
    return {
      ok: false,
      error: `Too large: the Wavefinity field cannot exceed ${fmt(maxField)} mm.`,
    };
  }
  return {
    ok: true, fieldX, fieldY, unitsX, unitsY, trimWidth: width,
    outerX: fieldX + extra, outerY: fieldY + extra,
  };
};

// The user's maximum finished outside rectangle (Fix 095). A Space that has
// no stored maximum is seeded from its current finished footprint, so the seed
// reproduces its current field exactly and can never grow the organizer. The
// visible inputs always keep the maximum; they are never overwritten with the
// smaller resolved finished size.
// A stored maximum is kept only when it is finite, positive, at least the finished
// outside size, and resolves (round down, same epsilon) to exactly the stored field;
// otherwise that axis is reseeded, so damaged metadata can never enlarge a Surface.
SP.surfaceMaxFor = space => {
  const { unit, gap } = SP.surfaceRules();
  const width = SP.surfacePresetMap()[space.trim_size];
  const axis = (field, value) => {
    const seed = SP.surfaceOutsideFor(Number(field), space.trim_size);
    if (value === null || value === undefined || value === "" || typeof value === "boolean") return seed;
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0 || number < seed - 1e-6) return seed;
    const units = Math.floor((number - (gap + 2 * width) + 1e-6) / unit);
    return units === Math.round(Number(field) / unit) ? number : seed;
  };
  return { x: axis(space.x, space.max_x_mm), y: axis(space.y, space.max_y_mm) };
};

SP.surfaceTrimLabel = key =>
  SP.surfacePresetRows().find(row => row.key === key)?.label || key || "";

// "35X × 29X — 280 × 232 mm" for a stored interior field.
SP.fieldText = (x, y) => {
  const { unit } = SP.surfaceRules();
  return `${fmt(x / unit)}X × ${fmt(y / unit)}X — ${fmt(x)} × ${fmt(y)} mm`;
};

SP.populateSurfaceTrim = () => {
  const select = document.getElementById("surface-trim");
  if (!select) return;
  const rows = SP.surfacePresetRows();
  select.innerHTML = [
    '<option value="" disabled>Choose trim size</option>',
    ...rows.map(row =>
      `<option value="${escapeHtml(row.key)}">${escapeHtml(row.label)}</option>`
    ),
  ].join("");
};

SP.pegboardStandards = () => state.catalog?.pegboard_rules?.standards || [];
SP.pegboardStandard = id => SP.pegboardStandards().find(row => row.id === id) || SP.pegboardStandards()[0];
SP.populatePegboardStandards = () => {
  const select = document.getElementById("pegboard-standard");
  if (!select) return;
  select.innerHTML = SP.pegboardStandards().map(row =>
    `<option value="${escapeHtml(row.id)}">${escapeHtml(row.name)}</option>`
  ).join("");
};
SP.resolvePegboard = () => {
  const standard = SP.pegboardStandard(document.getElementById("pegboard-standard")?.value);
  const mode = document.getElementById("pegboard-size-mode")?.value || "physical";
  if (!standard) return { ok: false, error: "Pegboard standards are unavailable." };
  let holesX, holesY, width, height, residualX = 0, residualY = 0;
  if (mode === "holes") {
    holesX = Number(document.getElementById("pegboard-holes-x")?.value);
    holesY = Number(document.getElementById("pegboard-holes-y")?.value);
    if (![holesX, holesY].every(value => Number.isInteger(value) && value >= 1 && value <= 500)) {
      return { ok: false, error: "Enter whole hole or slot counts from 1 to 500." };
    }
    width = holesX * standard.pitch_x_mm;
    height = holesY * standard.pitch_y_mm;
  } else {
    width = Number(document.getElementById("pegboard-x")?.value);
    height = Number(document.getElementById("pegboard-y")?.value);
    if (![width, height].every(value => Number.isFinite(value) && value > 0)) {
      return { ok: false, error: "Enter the Pegboard width and height in mm." };
    }
    holesX = Math.floor(width / standard.pitch_x_mm + 1e-9);
    holesY = Math.floor(height / standard.pitch_y_mm + 1e-9);
    if (holesX < 1 || holesY < 1) return { ok: false, error: "The board must contain at least one mount position." };
    if (holesX > 500 || holesY > 500) return { ok: false, error: "That board is too large. The limit is 500 mount positions per side." };
    residualX = width - holesX * standard.pitch_x_mm;
    residualY = height - holesY * standard.pitch_y_mm;
  }
  return { ok: true, standard, mode, holesX, holesY, width, height, residualX, residualY };
};

SP.drawerCapacity = mm => drawerSpaceCapacity(mm);
