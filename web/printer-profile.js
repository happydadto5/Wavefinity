/* Shared printer build volume. Local server writes are supplied by 084B. */
(() => {
  "use strict";
  const KEY = "wavefinity-printer-profile";
  const LEGACY = "wavefinity-base-trim-bed";
  const DEFAULT = Object.freeze({ x_mm: 256, y_mm: 256, z_mm: 256 });
  const UNREADABLE = "Printer Settings could not be read. Choose Reset Printer Settings to use the defaults.";
  let profile = { ...DEFAULT };
  let explicit = false;
  let malformed = "";
  const listeners = new Set();
  const stateListeners = new Set();
  const AXIS_NAMES = Object.freeze({ x: "Width (X)", y: "Depth (Y)", z: "Height (Z)" });
  const normalise = raw => {
    if (!raw || typeof raw !== "object") throw new Error("Enter printer build volume");
    const result = {};
    for (const key of ["x_mm", "y_mm", "z_mm"]) {
      const value = raw[key];
      if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) throw new Error(`Enter a positive printer ${AXIS_NAMES[key[0]]}`);
      result[key] = value;
    }
    return result;
  };
  const setMalformed = message => {
    if (malformed === message) return;
    malformed = message;
    for (const fn of stateListeners) fn(malformed);
  };
  const adopt = (raw, isExplicit) => {
    const next = normalise(raw);
    const changed = Object.keys(next).some(key => next[key] !== profile[key]);
    profile = next;
    explicit = !!isExplicit;
    setMalformed("");
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
    malformedMessage: () => malformed,
    set(raw) { return adopt(raw, true); },
    loadLocal({ profile: raw, explicit: setExplicit, malformed: bad }) {
      const result = adopt(raw || DEFAULT, setExplicit);
      if (bad) setMalformed(String(bad));
      return result;
    },
    async loadHosted() {
      try {
        const saved = localStorage.getItem(KEY);
        if (!saved) adopt(DEFAULT, false);
        else {
          const parsed = JSON.parse(saved);
          adopt(parsed.profile || parsed, parsed.explicit !== false);
        }
      } catch (_error) {
        adopt(DEFAULT, false);
        setMalformed(UNREADABLE);
      }
      return { profile: { ...profile }, explicit, malformed };
    },
    persistHosted(raw) {
      const next = normalise(raw);
      // Fix 096 A4: a failed persist must be visible; rethrow so the existing
      // onError path keeps working exactly as before.
      try {
        localStorage.setItem(KEY, JSON.stringify({ profile: next, explicit: true }));
      } catch (_error) {
        toast("The printer profile could not be remembered in this browser.", true);
        throw _error;
      }
      return adopt(next, true);
    },
    // Only the printer-profile key goes back to defaults, and the reset is
    // stored so the warning does not return at the next startup.
    resetHosted() {
      localStorage.removeItem(KEY);
      return adopt(DEFAULT, false);
    },
    readLegacyBaseTrimSeed,
    retireLegacyBaseTrim() { localStorage.removeItem(LEGACY); },
    summaryText() { return `Printer build volume — ${profile.x_mm} × ${profile.y_mm} × ${profile.z_mm} mm`; },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    mount(host, callbacks = {}) {
      host.replaceChildren();
      const warning = document.createElement("div");
      warning.className = "printer-profile-warning"; warning.hidden = true;
      const warningText = document.createElement("span");
      const resetButton = document.createElement("button");
      resetButton.type = "button"; resetButton.textContent = "Reset Printer Settings";
      warning.append(warningText, resetButton);
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
        const label = document.createElement("label"); label.textContent = `${AXIS_NAMES[axis]} mm`;
        const input = document.createElement("input");
        input.type = "number"; input.min = "0.01"; input.step = "any"; input.required = true;
        label.append(input); edit.append(label); inputs[axis] = input;
      }
      const save = document.createElement("button"); save.type = "submit"; save.textContent = "Save";
      const cancel = document.createElement("button"); cancel.type = "button"; cancel.textContent = "Cancel";
      edit.append(save, cancel); host.append(warning, row, edit);
      const render = () => {
        summary.textContent = api.summaryText();
        warning.hidden = !malformed; warningText.textContent = malformed;
      };
      render(); const unsubscribe = api.subscribe(render);
      stateListeners.add(render);
      change.addEventListener("click", () => {
        for (const axis of ["x", "y", "z"]) inputs[axis].value = profile[`${axis}_mm`];
        edit.hidden = false; row.hidden = true; inputs.x.focus();
      });
      cancel.addEventListener("click", () => { edit.hidden = true; row.hidden = false; });
      resetButton.addEventListener("click", async () => {
        try {
          if (callbacks.reset) await callbacks.reset(); else api.resetHosted();
          render();
        } catch (error) { callbacks.onError?.(error); }
      });
      edit.addEventListener("submit", async event => {
        event.preventDefault();
        try {
          const next = normalise(Object.fromEntries(["x", "y", "z"].map(axis => [`${axis}_mm`, Number(inputs[axis].value)])));
          if (callbacks.hosted || callbacks.mode === "hosted" || !callbacks.write) api.persistHosted(next);
          else { await callbacks.write(KEY, { profile: next, explicit: true }); adopt(next, true); }
          edit.hidden = true; row.hidden = false;
        } catch (error) { callbacks.onError?.(error); }
      });
      return () => { unsubscribe(); stateListeners.delete(render); host.replaceChildren(); };
    }
  };
  window.PrinterProfile = api;
})();
