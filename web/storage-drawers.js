/* Stable-ID cabinet state helpers. They do not mount application behavior. */
(() => {
  "use strict";
  const KIND = "storage_drawers";
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  let rules = null;
  const requireRules = () => {
    if (!rules) throw new Error("Storage Drawers rules are not configured");
    return rules;
  };
  const clone = value => structuredClone(value);
  const isSpace = space => space?.kind === KIND;
  const gridOf = space => space?.grid || space?.storage_drawers?.grid || "wavefinity";
  const gridProfile = space => {
    const profile = requireRules().grids.find(row => row.value === gridOf(space));
    if (!profile) throw new Error("Choose a valid cabinet grid");
    return profile;
  };
  const recordKeys = ["built_in_grid", "floor_grid", "floor_mode", "nominal_grid_mm", "physical_cavity_mm",
    "external_plate_clearance_per_side_mm", "external_plate_clearance_status", "seated_lift_mm",
    "seated_lift_status", "height_fit_verified"];
  const gridFields = space => {
    const fields = { grid: gridOf(space) };
    for (const key of recordKeys) {
      const value = space?.[key] !== undefined ? space[key] : space?.storage_drawers?.[key];
      if (value !== undefined) fields[key] = clone(value);
    }
    return fields;
  };
  const gridReadout = space => {
    if (gridOf(space) === "wavefinity") return "";
    const fields = gridFields(space), profile = gridProfile(space);
    const nominal = fields.nominal_grid_mm || [space.x, space.y];
    const cavity = fields.physical_cavity_mm;
    const size = values => values.map(value => Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 })).join(" × ") + " mm";
    const lift = fields.seated_lift_mm;
    return `${profile.label} · Nominal grid ${size(nominal)} · Printed cavity ${cavity ? size(cavity) : "unverified"} · ` +
      (fields.built_in_grid === "none" ? `None (owner-supplied baseplate, provisional cavity clearance) · Seated lift ${typeof lift === "number" && Number.isFinite(lift) && lift >= 0 ? `${lift} mm (measured)` : "unverified"}`
        : "Floor (built-in raised pocket grid)");
  };
  const descriptors = space => space?.storage_drawers?.drawers || [];
  const positive = value => typeof value === "number" && Number.isFinite(value) && value > 0;
  const whole = value => Number.isInteger(value) && value > 0;
  const choiceList = list => Array.isArray(list) && list.length > 0 && list.every(positive);
  // The one reader of the published catalog rules. Nothing else in the browser
  // carries a Storage Drawers constant; a missing or malformed rule fails closed.
  const catalogRules = catalog => {
    const published = catalog?.storage_drawers_rules;
    const baseUnit = catalog?.base_unit;
    const minDrawerHeight = catalog?.drawer_rules?.ordinary_bin_min_height_mm;
    const minUsableDrawerHeight = catalog?.drawer_rules?.min_usable_drawer_height_mm;
    if (!published || !Array.isArray(published.default_field_mm) || published.default_field_mm.length !== 2 ||
        !published.default_field_mm.every(positive) || !Array.isArray(catalog.grids) ||
        !["wavefinity", "gridfinity_half", "gridfinity"].every(grid => catalog.grids.some(row => row.value === grid && positive(row.pitch_mm) && (grid === "wavefinity" || (positive(row.height_unit_mm) && positive(row.container_floor_build_mm) && positive(row.container_floor_pocket_depth_mm))))) ||
        !positive(baseUnit) || !positive(minDrawerHeight) || !positive(minUsableDrawerHeight) ||
        !whole(published.min_units) || !whole(published.max_units) || published.max_units < published.min_units ||
        !whole(published.min_drawers) || !whole(published.max_drawers) || published.max_drawers < published.min_drawers ||
        !choiceList(published.drawer_fit_choices_mm) || !published.drawer_fit_choices_mm.includes(published.default_drawer_fit_mm) ||
        !choiceList(published.frame_width_choices_mm) || !published.frame_width_choices_mm.includes(published.default_frame_width_mm) ||
        !whole(published.label_limit) || !positive(published.default_usable_height_mm) || !positive(published.max_usable_height_mm)) {
      throw new Error("Storage Drawers catalog rules are unavailable");
    }
    return Object.freeze({
      baseUnit, minDrawerHeight, minUsableDrawerHeight,
      defaultField: Object.freeze([...published.default_field_mm]),
      grids: Object.freeze(catalog.grids.map(row => Object.freeze({ ...row }))),
      minUnits: published.min_units, maxUnits: published.max_units,
      minDrawers: published.min_drawers, maxDrawers: published.max_drawers,
      fitChoices: Object.freeze([...published.drawer_fit_choices_mm]), defaultFit: published.default_drawer_fit_mm,
      frameChoices: Object.freeze([...published.frame_width_choices_mm]), defaultFrame: published.default_frame_width_mm,
      labelLimit: published.label_limit, defaultHeight: published.default_usable_height_mm,
      maxUsableHeight: published.max_usable_height_mm,
    });
  };
  const validate = space => {
    const { baseUnit, minDrawerHeight, minUsableDrawerHeight, maxUsableHeight, fitChoices, defaultFit, minUnits, maxUnits, minDrawers, maxDrawers } = requireRules();
    if (!isSpace(space)) throw new Error("Expected Storage Drawers Space");
    const profile = gridProfile(space), pitch = profile.pitch_mm;
    if (gridOf(space) !== "wavefinity" && !["floor", "none"].includes(space.built_in_grid ?? space.storage_drawers?.built_in_grid)) throw new Error("Choose Floor or None for a Gridfinity cabinet");
    const lift = space.storage_drawers?.seated_lift_mm ?? space.seated_lift_mm;
    if (gridOf(space) !== "wavefinity" && lift != null && (typeof lift !== "number" || !Number.isFinite(lift) || lift < 0)) throw new Error("Seated lift must be a measured non-negative height or unverified");
    const rows = descriptors(space);
    if (!Array.isArray(rows) || rows.length < minDrawers || rows.length > maxDrawers) throw new Error(`Number of drawers must be ${minDrawers}–${maxDrawers}`);
    const seen = new Set();
    const fit = fitChoices.includes(space?.storage_drawers?.drawer_fit_mm) ? space.storage_drawers.drawer_fit_mm : defaultFit;
    for (const row of rows) {
      if (!UUID.test(row?.id || "") || seen.has(row.id)) throw new Error("Drawer ID is missing, malformed, or duplicated");
      seen.add(row.id);
      if (typeof row.height_mm !== "number" || !Number.isFinite(row.height_mm) || row.height_mm < minDrawerHeight) throw new Error("Invalid drawer height");
      // Story 2763: usable height (stored height + fit) must be at least
      // minUsableDrawerHeight, the server's ordinary-bin minimum (no added 2 mm).
      if (row.height_mm + fit < minUsableDrawerHeight) throw new Error("Invalid drawer height");
      if (row.height_mm + fit > maxUsableHeight) throw new Error(`Drawer usable height must be at most ${maxUsableHeight} mm`);
    }
    for (const axis of ["x", "y"]) {
      const units = space[axis] / baseUnit;
      const minimum = gridOf(space) === "wavefinity" ? minUnits : pitch / baseUnit;
      if (!Number.isInteger(units) || units < minimum || units > maxUnits || !Number.isInteger(space[axis] / pitch)) throw new Error(`Space ${axis} must use whole ${pitch} mm cells within the cabinet size range`);
    }
    return rows;
  };
  const projection = (space, layout) => {
    const rows = validate(space);
    const next = clone(layout || {});
    const byId = new Map();
    for (const row of next.drawers || []) {
      if (!UUID.test(row?.id || "") || byId.has(row.id)) throw new Error("Layout drawer ID is missing, malformed, or duplicated");
      byId.set(row.id, row);
    }
    const ids = new Set(rows.map(row => row.id));
    for (const [id, row] of byId) if (!ids.has(id) && row.placements?.length) throw new Error("A removed drawer still holds bins");
    const seenRows = new Set();
    next.drawers = rows.map((row, index) => {
      const old = byId.get(row.id) || {};
      const placements = clone(old.placements || []);
      for (const placed of placements) {
        if (placed.bin && seenRows.has(placed.bin)) throw new Error("One Inventory row is placed in more than one drawer");
        if (placed.bin) seenRows.add(placed.bin);
      }
      return { ...old, id: row.id, name: `Drawer ${index + 1}`, width: space.x, depth: space.y,
        height: row.height_mm + space.storage_drawers.drawer_fit_mm, clearance: 0, boundary: "mating", placements,
        ...(gridOf(space) !== "wavefinity" ? gridFields(space) : {}) };
    });
    next.active = ids.has(next.active) ? next.active : rows[0].id;
    next.space = clone(space);
    return next;
  };
  const key = (draft, printer) => JSON.stringify([draft?.name, draft?.x, draft?.y, gridFields(draft), draft?.storage_drawers, printer]);
  const api = {
    KIND, isSpace, catalogRules, gridOf, gridProfile, gridFields, gridReadout,
    configureRules(catalog) { rules = catalogRules(catalog); return rules; },
    rules() { return requireRules(); },
    unitCounts(space) { validate(space); const pitch = gridProfile(space).pitch_mm; return [space.x / pitch, space.y / pitch]; },
    drawerDescriptors(space) { return clone(validate(space)); },
    drawerName(space, id) { const index = validate(space).findIndex(row => row.id === id); return index < 0 ? null : `Drawer ${index + 1}`; },
    activeDrawerLimits(space, layout) {
      const rows = validate(space); const row = rows.find(one => one.id === layout?.active) || rows[0];
      return { x: space.x, y: space.y, z: row.height_mm + space.storage_drawers.drawer_fit_mm, drawer_id: row.id, ...gridFields(space) };
    },
    drawerHoldingRow(layout, rowId) { return (layout?.drawers || []).find(drawer => drawer.placements?.some(p => p.bin === rowId))?.id || null; },
    rowLocationText(layout, rowId) {
      const id = api.drawerHoldingRow(layout, rowId);
      const number = (layout?.drawers || []).findIndex(row => row.id === id) + 1;
      return number ? `Placed · Drawer ${number}` : "Not placed";
    },
    reconcileProjection: projection,
    prepareCreateDraft(raw) {
      const space = clone(raw);
      if (!isSpace(space) || !Array.isArray(descriptors(space))) throw new Error("Storage Drawers draft is missing");
      for (const row of descriptors(space)) {
        if (row.id === undefined) row.id = crypto.randomUUID().toLowerCase();
        delete row.temp_key;
      }
      validate(space); space.z = descriptors(space).reduce((sum, row) => sum + row.height_mm, 0);
      return space;
    },
    structuralDraftKey: key,
    async requestSummary({ spaceDraft, printerProfile, request, adopt }) {
      const requestKey = key(spaceDraft, printerProfile);
      const response = await request({ space: clone(spaceDraft), printer_profile: clone(printerProfile) });
      if (key(spaceDraft, printerProfile) === requestKey) adopt(response);
      return response;
    },
    // Runs cabinet mutations one at a time. Resolves with the result only when
    // it was adopted into the same current Space; a stale or superseded result
    // resolves null, so no caller may announce success for it.
    createMutationController(callbacks) {
      let tail = Promise.resolve(); let generation = 0;
      return {
        run(operation, payload) {
          const job = async () => {
            const context = callbacks.captureContext();
            await callbacks.settleLayout();
            if (!callbacks.isCurrent(context)) return null;
            const epoch = ++generation;
            callbacks.advanceLayoutEpoch?.();
            const result = await callbacks.mutate(operation, payload);
            if (epoch === generation && callbacks.isCurrent(context)) {
              callbacks.adopt(result);
              return result;
            }
            return null;
          };
          tail = tail.then(job, job);
          return tail;
        },
        invalidate() { generation += 1; }
      };
    }
  };
  window.StorageDrawers = api;
})();
