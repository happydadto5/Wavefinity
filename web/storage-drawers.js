/* Stable-ID cabinet state helpers. They do not mount application behavior. */
(() => {
  "use strict";
  const KIND = "storage_drawers";
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
  const clone = value => structuredClone(value);
  const isSpace = space => space?.kind === KIND;
  const descriptors = space => space?.storage_drawers?.drawers || [];
  const validate = space => {
    if (!isSpace(space)) throw new Error("Expected Storage Drawers Space");
    const rows = descriptors(space);
    if (!Array.isArray(rows) || rows.length < 1 || rows.length > 32) throw new Error("Number of drawers must be 1–32");
    const seen = new Set();
    for (const row of rows) {
      if (!UUID.test(row?.id || "") || seen.has(row.id)) throw new Error("Drawer ID is missing, malformed, or duplicated");
      seen.add(row.id);
      if (typeof row.height_mm !== "number" || !Number.isFinite(row.height_mm) || row.height_mm <= 0) throw new Error("Invalid drawer height");
    }
    for (const axis of ["x", "y"]) {
      const units = space[axis] / 8;
      if (!Number.isInteger(units) || units < 6 || units > 250) throw new Error(`Space ${axis} must be 6–250 whole units`);
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
        height: row.height_mm, clearance: 0, boundary: "mating", placements };
    });
    next.active = ids.has(next.active) ? next.active : rows[0].id;
    next.space = clone(space);
    return next;
  };
  const key = (draft, printer) => JSON.stringify([draft?.name, draft?.x, draft?.y, draft?.storage_drawers, printer]);
  const api = {
    KIND, isSpace,
    unitCounts(space) { validate(space); return [space.x / 8, space.y / 8]; },
    drawerDescriptors(space) { return clone(validate(space)); },
    drawerName(space, id) { const index = validate(space).findIndex(row => row.id === id); return index < 0 ? null : `Drawer ${index + 1}`; },
    activeDrawerLimits(space, layout) {
      const rows = validate(space); const row = rows.find(one => one.id === layout?.active) || rows[0];
      return { x: space.x, y: space.y, z: row.height_mm, drawer_id: row.id };
    },
    drawerHoldingRow(layout, rowId) { return (layout?.drawers || []).find(drawer => drawer.placements?.some(p => p.bin === rowId))?.id || null; },
    rowLocationText(layout, rowId) {
      const id = api.drawerHoldingRow(layout, rowId);
      const number = (layout?.drawers || []).findIndex(row => row.id === id) + 1;
      return number ? `Placed · Drawer ${number}` : "Unplaced";
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
            if (epoch === generation && callbacks.isCurrent(context)) callbacks.adopt(result);
            return result;
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
