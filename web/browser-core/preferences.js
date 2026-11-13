// B14 imports ROUTES in the window runtime. No folder paths or credentials
// belong in this origin-local preference record.
const KEY = 'browser-preferences-v1';
const UI_KEYS = ['ui', 'theme', 'units', 'sidebar', 'last_space_kind'];
let tail = Promise.resolve();
let initialization;
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const values = (operation, payload) => WFLocalAPI.spaceValues(operation, payload);

async function initialPreferences() {
  const saved = await WFFileSystem.load(KEY);
  if (saved !== null && !object(saved)) throw new Error('Saved preferences could not be read. Import a saved preferences file to recover them.');
  if (saved !== null) return saved;
  // One-time migration from the app's previous origin-local controls. Leave
  // the old values untouched until the replacement transaction commits.
  const prefs = {};
  try {
    const printer = JSON.parse(localStorage.getItem('wavefinity-printer-profile') || 'null');
    if (printer && printer.explicit !== false) {
      const normalized = await values('printer-profile', { profile: printer.profile || printer });
      Object.assign(prefs, normalized.preferences);
    }
  } catch (_error) { prefs.printer_profile_malformed = 'Printer Settings could not be read. Choose Reset Printer Settings to use the defaults.'; }
  try {
    const connector = JSON.parse(localStorage.getItem('wavefinity-connector-settings-v1') || 'null');
    if (connector) Object.assign(prefs, await values('preferences', { connector_settings: connector }));
  } catch (_error) { prefs.preference_warning = 'Previous connector settings could not be read. Choose the connector settings again.'; }
  await WFFileSystem.save(KEY, prefs);
  try {
    if (!prefs.printer_profile_malformed) localStorage.removeItem('wavefinity-printer-profile');
    if (!prefs.preference_warning) localStorage.removeItem('wavefinity-connector-settings-v1');
  } catch (_error) { /* The committed IndexedDB record is now authoritative. */ }
  return prefs;
}

export async function loadPreferences() {
  if (!initialization) initialization = initialPreferences().catch(error => { initialization = null; throw error; });
  await initialization;
  const saved = await WFFileSystem.load(KEY);
  if (!object(saved)) throw new Error('Saved preferences could not be read.');
  return saved;
}

export function mutatePreferences(change, { recover = false } = {}) {
  const pending = tail.then(async () => {
    let prefs;
    try { prefs = await loadPreferences(); }
    catch (error) { if (!recover) throw error; prefs = {}; }
    await change(prefs);
    await WFFileSystem.save(KEY, prefs);
    initialization = Promise.resolve();
    return prefs;
  });
  tail = pending.catch(() => {});
  return pending;
}

async function validated(raw) {
  if (!object(raw)) throw new Error('Preferences must be an object.');
  const result = await values('preferences', raw);
  for (const key of UI_KEYS) if (Object.hasOwn(raw, key)) result[key] = structuredClone(raw[key]);
  const printerKeys = ['printer_build_x_mm', 'printer_build_y_mm', 'printer_build_z_mm'];
  if (printerKeys.some(key => Object.hasOwn(raw, key))) {
    const profile = Object.fromEntries(['x_mm', 'y_mm', 'z_mm'].map((axis, i) => [axis, raw[printerKeys[i]]]));
    const normalized = await values('printer-profile', { profile });
    Object.assign(result, normalized.preferences);
  }
  return result;
}

export async function exportPreferences() {
  await tail;
  return { format: 'wavefinity-preferences/1', preferences: await loadPreferences() };
}

export async function importPreferences(backup) {
  if (backup?.format !== 'wavefinity-preferences/1') throw new Error('Choose a Wavefinity preferences export.');
  const update = await validated(backup.preferences);
  return mutatePreferences(prefs => Object.assign(prefs, update), { recover: true });
}

async function preferences(payload = {}) {
  if (payload.action === 'export') return exportPreferences();
  if (payload.action === 'import') return { preferences: await importPreferences(payload.backup) };
  const update = await validated(payload);
  return { preferences: Object.keys(update).length
    ? await mutatePreferences(prefs => Object.assign(prefs, update)) : await loadPreferences() };
}

async function printerProfile(payload = {}) {
  if (payload.profile === undefined && payload.reset !== true) {
    const { preferences: ignored, ...reply } = await values('printer-profile', { preferences: await loadPreferences() });
    return reply;
  }
  let reply;
  await mutatePreferences(async prefs => {
    const result = await values('printer-profile', { ...payload, preferences: prefs });
    for (const key of Object.keys(prefs)) delete prefs[key];
    Object.assign(prefs, result.preferences);
    const { preferences: ignored, ...state } = result;
    reply = state;
  });
  return reply;
}

export const ROUTES = new Map([
  ['/api/preferences', preferences],
  ['/api/space/printer-profile', printerProfile],
]);
