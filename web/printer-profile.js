/* Shared printer build volume. Integration supplies persistence callbacks in 084B. */
(() => {
  "use strict";
  const KEY = "wavefinity-printer-profile";
  const LEGACY = "wavefinity-base-trim-bed";
  const DEFAULT = Object.freeze({ x_mm: 256, y_mm: 256, z_mm: 256 });
  let profile = { ...DEFAULT };
  let explicit = false;
  let durable = false;
  let persistence = null;
  const listeners = new Set();
  const normalise = raw => {
    if (!raw || typeof raw !== "object") throw new Error("Enter printer build volume");
    const result = {};
    for (const key of ["x_mm", "y_mm", "z_mm"]) {
      const value = raw[key];
      if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) throw new Error(`Enter a positive printer ${key}`);
      result[key] = value;
    }
    return result;
  };
  const adopt = (raw, isExplicit) => {
    const next = normalise(raw);
    const changed = Object.keys(next).some(key => next[key] !== profile[key]);
    profile = next;
    explicit = !!isExplicit;
    if (changed) for (const fn of listeners) fn({ ...profile });
    return { ...profile };
  };
  const readLegacyBaseTrimSeed = () => {
    try {
      const old = JSON.parse(localStorage.getItem(LEGACY) || "null");
      const x = old?.["space-structural-bed-x"];
      const y = old?.["space-structural-bed-y"];
      return typeof x === "number" && Number.isFinite(x) && x > 0 &&
        typeof y === "number" && Number.isFinite(y) && y > 0 ? { x_mm: x, y_mm: y, z_mm: 256 } : null;
    } catch (_) { return null; }
  };
  const api = {
    DEFAULT, normalise, current: () => ({ ...profile }),
    set(raw) { durable = false; return adopt(raw, true); },
    loadLocal({ profile: raw, explicit: setExplicit }) { durable = !!setExplicit; return adopt(raw || DEFAULT, setExplicit); },
    async loadHosted() {
      const saved = persistence?.read ? await persistence.read(KEY) : null;
      if (!saved) return { profile: { ...profile }, explicit };
      const parsed = typeof saved === "string" ? JSON.parse(saved) : saved;
      adopt(parsed.profile || parsed, parsed.explicit !== false);
      durable = explicit;
      return { profile: { ...profile }, explicit };
    },
    readLegacyBaseTrimSeed,
    retireLegacyBaseTrim() { if (durable) localStorage.removeItem(LEGACY); },
    summaryText() { return `Printer build volume — ${profile.x_mm} × ${profile.y_mm} × ${profile.z_mm} mm`; },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    mount(host, callbacks = {}) {
      persistence = callbacks;
      host.replaceChildren();
      const row = document.createElement("div");
      row.className = "sd-printer-row";
      const summary = document.createElement("span");
      const change = document.createElement("button");
      change.type = "button"; change.textContent = "Change";
      row.append(summary, change);
      const edit = document.createElement("form");
      edit.className = "sd-printer-edit"; edit.hidden = true;
      const inputs = {};
      for (const axis of ["x", "y", "z"]) {
        const label = document.createElement("label"); label.textContent = `${axis.toUpperCase()} mm`;
        const input = document.createElement("input");
        input.type = "number"; input.min = "0.01"; input.step = "any"; input.required = true;
        label.append(input); edit.append(label); inputs[axis] = input;
      }
      const save = document.createElement("button"); save.type = "submit"; save.textContent = "Save";
      const cancel = document.createElement("button"); cancel.type = "button"; cancel.textContent = "Cancel";
      edit.append(save, cancel); host.append(row, edit);
      const render = () => { summary.textContent = api.summaryText(); };
      render(); const unsubscribe = api.subscribe(render);
      change.addEventListener("click", () => {
        for (const axis of ["x", "y", "z"]) inputs[axis].value = profile[`${axis}_mm`];
        edit.hidden = false; row.hidden = true; inputs.x.focus();
      });
      cancel.addEventListener("click", () => { edit.hidden = true; row.hidden = false; });
      edit.addEventListener("submit", async event => {
        event.preventDefault();
        try {
          const next = normalise(Object.fromEntries(["x", "y", "z"].map(axis => [`${axis}_mm`, Number(inputs[axis].value)])));
          if (callbacks.write) await callbacks.write(KEY, { profile: next, explicit: true });
          durable = !!callbacks.write;
          adopt(next, true); edit.hidden = true; row.hidden = false;
        } catch (error) { callbacks.onError?.(error); }
      });
      return () => { unsubscribe(); host.replaceChildren(); };
    }
  };
  window.PrinterProfile = api;
})();
