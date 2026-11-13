// B09 owns browser persistence. B14 registers this JS map, never in Python.
// Existing SP helpers own metadata formats and inventory migration semantics.
const fs = () => WFFileSystem;
const values = (operation, payload) => WFLocalAPI.spaceValues(operation, payload);
async function currentValues(operation, payload) {
  const captured = stamp(), result = await values(operation, payload);
  assertCurrent(captured);
  return result;
}
const stale = () => Object.assign(new Error('The Space or design changed before this action finished. Its result was not applied to the current Space; files already saved remain in their original folder.'), { status: 409, kind: 'STALE_SPACE' });
const stamp = () => ({ id: state.activeSpaceId, epoch: WFLocalAPI.designEpoch, preview: state.previewRequest, folder: state.browserFolder, relocating: state.relocating });
const assertCurrent = captured => {
  if (captured.id !== state.activeSpaceId || captured.epoch !== WFLocalAPI.designEpoch ||
      captured.preview !== state.previewRequest || captured.folder !== state.browserFolder || captured.relocating !== state.relocating) throw stale();
};
const nameForFolder = raw => {
  const name = String(raw || '').trim();
  if (!name || name.length > 80 || /[<>:"/\\|?*\x00-\x1f]/.test(name) || /[. ]$/.test(name) ||
      /^(\.|\.\.|con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) {
    throw new Error('Give the Space a valid folder name of at most 80 characters.');
  }
  return name;
};
async function folderFor(payload = {}) {
  let folder = payload.folder || payload.output;
  if (!folder && payload.space_id) folder = (await SP.loadHostedRecent()).find(row => row.space_id === payload.space_id);
  if (!folder) folder = state.browserFolder;
  if (folder?.kind === 'directory') folder = { handle: folder, name: folder.name };
  if (!folder?.handle) throw new Error('Choose a writable folder to save this Space. Files have not been autosaved.');
  return { ...folder, name: folder.folder_name || folder.handle.name };
}
async function permission(handle, prompt = true) {
  const allowed = prompt ? await fs().requestReadWritePermission(handle) : await fs().queryReadWritePermission(handle);
  if (!allowed) throw new Error('Folder access is unavailable. Choose the folder again and allow read/write access. Files have not been autosaved.');
}
async function inspectFolder(folder, expected = null) {
  await permission(folder.handle);
  const info = await SP.inspectHosted(folder);
  SP.assertExpectedHostedIdentity(info, expected);
  return info;
}
async function recent() { return SP.loadHostedRecent(); }
async function reply(folder, info = null) {
  const resolved = folder ? { ...(info || await inspectFolder(folder)), browser_folder: folder } : null;
  return { folder: resolved, space: resolved, recent: await recent() };
}
async function remember(folder, info, captured) {
  assertCurrent(captured);
  // Duplicate identities are never adopted just because a copied folder was
  // picked. A deliberate Copy creates a fresh identity before registration.
  for (const row of await recent()) {
    if (info.space_id && row.space_id === info.space_id && !(await SP.sameHostedHandle(row.handle, folder.handle))) {
      throw new Error('Two folders have the same Space ID. Open the original Space and use Copy Space.');
    }
  }
  assertCurrent(captured);
  await fs().queueFolderWrite(folder.handle, () => {
    assertCurrent(captured);
    return fs().save('active', { ...folder, space_id: info.space_id });
  });
  assertCurrent(captured);
  await SP.rememberHostedRecent(folder, info, () => assertCurrent(captured));
}
async function inspect(payload = {}) {
  const captured = stamp(), folder = await folderFor(payload);
  const result = await reply(folder, await inspectFolder(folder, payload.space_id));
  assertCurrent(captured);
  return result;
}
async function open(payload = {}) {
  const captured = stamp(), folder = await folderFor(payload);
  const info = await inspectFolder(folder, payload.space_id);
  if (info.needs_setup) throw new Error('Complete this folder’s Space setup before opening it.');
  assertCurrent(captured);
  await fs().queueFolderWrite(folder.handle, async () => {
    assertCurrent(captured);
    if (info.inventory) await SP.readInventoryFor(folder, { migrate: true });
    if (info.needs_identity_migration || (info.metadata_version && info.metadata_version < FOLDER_METADATA_VERSION)) {
      await SP._writeMetadataNow(folder.handle, info.folder_mode, null, info.inventory, {},
        info.folder_mode === 'space' ? { preserveSpace: true, expectedSpaceId: info.space_id } : {});
    }
  });
  const current = await inspectFolder(folder, payload.space_id);
  await remember(folder, current, captured);
  assertCurrent(captured);
  return reply(folder, current);
}
function pick(payload = {}) {
  // Invoke the picker before any await/worker initialization spends the click.
  return fs().pickDirectory(payload.space_root ? { id: 'wavefinity', startIn: 'documents' } : {}).then(result => {
    if (result.status === 'cancelled') return { folder: null, status: 'cancelled' };
    if (result.status !== 'ok') throw new Error(result.status === 'unsupported'
      ? 'This browser cannot save Spaces to folders. Use explicit export to keep your work.'
      : 'Choose the folder again and allow read/write access.');
    return { folder: { handle: result.handle, name: result.handle.name }, status: 'ok' };
  });
}
async function home() {
  const record = await fs().load('home');
  if (!record?.handle) throw new Error('Choose a Space storage folder first.');
  await permission(record.handle);
  return record;
}
async function noDefinedSpace() {
  if (!fs().supportsDirectoryPicker()) return { folder: null, space: null, recent: await recent(), autosave: false };
  const captured = stamp(), parent = await home();
  const handle = await parent.handle.getDirectoryHandle('No Defined Space', { create: true });
  const folder = { handle, name: handle.name, home_name: handle.name };
  await fs().queueFolderWrite(handle, async () => {
    const info = await inspectFolder(folder);
    if (!info.exists) {
      assertCurrent(captured);
      await SP._writeMetadataNow(handle, 'design', null, true);
    }
  });
  return open({ folder });
}
async function useUntyped(payload) {
  const captured = stamp(), folder = await folderFor(payload);
  await fs().queueFolderWrite(folder.handle, async () => {
    const info = await inspectFolder(folder, payload.space_id);
    if (info.folder_mode === 'space' && SP.authoritativeTypedSource(info)) throw new Error('This folder already holds a typed Space.');
    assertCurrent(captured);
    await SP._writeMetadataNow(folder.handle, 'design', null, info.inventory);
  });
  return open({ folder });
}
async function inventory(payload) {
  const captured = stamp(), folder = await folderFor(payload);
  await fs().queueFolderWrite(folder.handle, async () => {
    const info = await inspectFolder(folder, payload.space_id);
    const enabled = payload.inventory !== false;
    if (info.folder_mode === 'space' && !enabled) throw new Error('Space planning needs this folder’s inventory turned on.');
    assertCurrent(captured);
    await SP._writeMetadataNow(folder.handle, info.folder_mode, null, enabled, {}, info.folder_mode === 'space'
      ? { preserveSpace: true, expectedSpaceId: info.space_id } : {});
  });
  assertCurrent(captured);
  return reply(folder);
}
async function metadataChange(payload, fields, requireIdentity = false) {
  const captured = stamp(), folder = await folderFor(payload);
  if (requireIdentity && !SP.validUuid(payload.space_id)) throw new Error('A resume checkpoint must name its Space ID.');
  if (requireIdentity && (typeof payload.resume_pending !== 'boolean' ||
      (payload.resume_design !== null && (!payload.resume_design || typeof payload.resume_design !== 'object' || Array.isArray(payload.resume_design))))) {
    throw new Error('Resume needs an object or null design and a boolean pending flag.');
  }
  const changes = Object.fromEntries(fields.filter(key => Object.hasOwn(payload, key)).map(key => [key, structuredClone(payload[key])]));
  await fs().queueFolderWrite(folder.handle, async () => {
    const info = await inspectFolder(folder, payload.space_id);
    if (info.folder_mode !== 'space') throw new Error('These settings belong to a typed Space.');
    // A captured outgoing checkpoint may finish on its original folder. It
    // cannot adopt state; expectedSpaceId is checked again inside the write.
    if (!requireIdentity) assertCurrent(captured);
    await SP._writeMetadataNow(folder.handle, 'space', null, true, changes,
      { preserveSpace: true, expectedSpaceId: payload.space_id || info.space_id });
  });
  return reply(folder);
}
async function configure(payload, operation) {
  const captured = stamp();
  let folder, created = false, parent;
  if (payload.output || payload.folder) folder = await folderFor(payload);
  else {
    parent = await home();
    const name = nameForFolder(payload.name);
    for await (const [entry] of parent.handle.entries()) {
      if (entry.toLowerCase() === name.toLowerCase()) throw new Error('That folder already exists. Choose another name or configure the existing folder.');
    }
    assertCurrent(captured);
    folder = { handle: await parent.handle.getDirectoryHandle(name, { create: true }), name, home_name: name };
    created = true;
  }
  try {
    await fs().queueFolderWrite(folder.handle, async () => {
      const info = await inspectFolder(folder, payload.space_id);
      if (operation === 'create-text' && info.exists) throw new Error('This folder already contains Wavefinity data. Use Configure Existing.');
      if (operation === 'update-text' && info.folder_mode !== 'space') throw new Error('Open a typed Space before editing it.');
      const result = await values(operation, { ...payload,
        ...(operation === 'update-text' ? { kind: info.space.kind } : {}),
        inventory_text: info.inventory_text, inventory_title: folder.name });
      assertCurrent(captured);
      const filename = SP.inventoryFilenameFor(folder);
      const prior = await fs().readText(folder.handle, filename);
      await fs().writeText(folder.handle, filename, result.inventory_text);
      try {
        await SP._writeMetadataNow(folder.handle, 'space', result.layout.space, true, {},
          info.space_id ? { expectedSpaceId: info.space_id } : {});
      } catch (error) {
        try {
          if (prior === null) await fs().removeFile(folder.handle, filename);
          else await fs().writeText(folder.handle, filename, prior);
        } catch (_restore) { throw new Error('Space save failed and Inventory could not be restored. Reopen the folder to recover; autosave did not complete.'); }
        throw error;
      }
    });
  } catch (error) {
    if (created) {
      // Only remove files this operation owns; never recursively delete a
      // directory into which the user may have placed unrelated files.
      if (!(await fs().fileExists(folder.handle, FOLDER_METADATA))) {
        const entries = [];
        for await (const entry of folder.handle.entries()) entries.push(entry);
        if (!entries.length) await parent.handle.removeEntry(folder.name);
      }
    }
    throw error;
  }
  const info = await inspectFolder(folder);
  let warning;
  try { await remember(folder, info, captured); }
  catch (error) { warning = `The Space files were saved, but the current Space could not be remembered: ${error.message}`; }
  assertCurrent(captured);
  return { ...await reply(folder, info), ...(warning ? { warning } : {}) };
}

async function otherSpaces() {
  const captured = stamp();
  const parent = await fs().load('home'), spaces = [];
  if (parent?.handle && await fs().queryReadWritePermission(parent.handle)) {
    for await (const [name, handle] of parent.handle.entries()) {
      if (handle.kind !== 'directory') continue;
      const folder = { handle, name, home_name: name };
      try {
        await permission(handle, false);
        const info = await inspectFolder(folder);
        if (info.folder_mode === 'space' && info.space_id !== state.activeSpaceId) spaces.push({ ...info, ...folder });
      } catch (error) { spaces.push({ ...folder, invalid: true, error: error.message }); }
    }
  }
  assertCurrent(captured);
  return { other_spaces: spaces };
}
async function storageState() {
  const parent = await fs().load('home');
  return { storage: { parent: parent?.handle?.name || null, root: parent?.handle?.name || null,
    leftover: parent?.leftover || null,
    explicit: Boolean(parent?.handle), first_run: !parent?.handle,
    unavailable: Boolean(parent?.handle) && !(await fs().queryReadWritePermission(parent.handle)),
    autosave: fs().supportsDirectoryPicker() && Boolean(parent?.handle) && await fs().queryReadWritePermission(parent.handle), browser: true } };
}
async function startup() {
  const captured = stamp(), saved = await fs().load('active');
  const recovery = await fs().load('storage-change-recovery-v1');
  const base = { ...await reply(null), ...await storageState(), ...await otherSpaces(), autosave: false,
    ...(recovery ? { warning: 'A storage change was interrupted. The original location remains selected; both folders were retained for recovery.' } : {}) };
  if (!saved?.handle || !fs().supportsDirectoryPicker()) return base;
  if (!(await fs().queryReadWritePermission(saved.handle))) return { ...base, reconnect_required: true };
  try {
    const folder = { ...saved, name: saved.handle.name };
    const info = await inspectFolder(folder, saved.space_id);
    assertCurrent(captured);
    return { ...base, ...await reply(folder, info), autosave: !info.needs_setup };
  } catch (error) { return { ...base, warning: error.message }; }
}
async function forget(payload) {
  const captured = stamp();
  const rows = await recent(), kept = [];
  const folder = payload.output || payload.folder ? await folderFor(payload) : null;
  for (const row of rows) {
    if (payload.space_id && row.space_id === payload.space_id) continue;
    if (folder && await SP.sameHostedHandle(row.handle, folder.handle)) continue;
    kept.push(row);
  }
  const active = await fs().load('active');
  assertCurrent(captured);
  await SP.saveHostedRecent(kept);
  if (active && ((payload.space_id && active.space_id === payload.space_id) ||
      (folder && await SP.sameHostedHandle(active.handle, folder.handle)))) await fs().save('active', null);
  return reply(null);
}
async function actionLocation(payload) {
  if (!SP.validUuid(payload.space_id) || payload.space_id !== state.activeSpaceId) throw stale();
  const folder = await folderFor(payload), parent = await home();
  const path = await parent.handle.resolve(folder.handle);
  if (!path || path.length !== 1) throw new Error('Open this Space inside your selected storage folder before copying or deleting it.');
  const info = await inspectFolder(folder, payload.space_id);
  if (info.folder_mode !== 'space') throw new Error('Open a typed Space first.');
  return { folder, parent: parent.handle, entry: path[0], info };
}
async function copy(payload) {
  const captured = stamp(), source = await actionLocation(payload);
  await SP.flushOutgoingResumeCheckpoint();
  return fs().queueFolderWrite(source.folder.handle, async () => {
    const names = [];
    for await (const [name] of source.parent.entries()) names.push(name);
    let name;
    do {
      name = nameForFolder((await values('copy-name', { name: source.info.space.name, names })).name);
      if (!names.some(entry => entry.toLowerCase() === name.toLowerCase())) break;
      names.push(name);
    } while (true);
    const info = await inspectFolder(source.folder, payload.space_id);
    const inventory = await values('copy-text', { inventory_text: info.inventory_text, name,
      space: info.space, resume_design: info.resume_design });
    assertCurrent(captured);
    const handle = await source.parent.getDirectoryHandle(name, { create: true });
    const destination = { handle, name, home_name: name };
    const journal = [];
    try {
      await fs().copyDirectory(source.folder.handle, handle, [FOLDER_METADATA], journal);
      const { current } = await SP.readMetadata(source.folder.handle);
      if (!journal.some(row => row.parent === handle && row.name === INVENTORY_FILENAME) && await fs().fileExists(handle, INVENTORY_FILENAME)) throw new Error('A file appeared in the copy destination. Nothing was overwritten.');
      journal.push({ parent: handle, name: INVENTORY_FILENAME, kind: 'file', sha256: await fs().sha256Blob(new Blob([inventory.inventory_text])) });
      await fs().writeText(handle, INVENTORY_FILENAME, inventory.inventory_text);
      if (await fs().fileExists(handle, FOLDER_METADATA)) throw new Error('Space metadata appeared in the copy destination. It was not overwritten.');
      const metadataText = JSON.stringify({ ...current.data,
        space_id: crypto.randomUUID(), space: { ...current.data.space, name } }, null, 2);
      journal.push({ parent: handle, name: FOLDER_METADATA, kind: 'file', sha256: await fs().sha256Blob(new Blob([metadataText])) });
      await fs().writeText(handle, FOLDER_METADATA, metadataText);
    } catch (error) {
      try { await fs().rollbackCopy(journal); await source.parent.removeEntry(name); }
      catch (_cleanup) { throw new Error(`Copy failed; the incomplete folder “${name}” could not be removed. The original Space is unchanged.`); }
      throw error;
    }
    assertCurrent(captured);
    await SP.rememberHostedRecent(destination, await inspectFolder(destination), () => assertCurrent(captured));
    return { name, recent: await recent(), ...await otherSpaces() };
  });
}
async function deleteSpace(payload) {
  const captured = stamp(), source = await actionLocation(payload);
  await SP.flushOutgoingResumeCheckpoint();
  await fs().queueFolderWrite(source.folder.handle, async () => {
    await inspectFolder(source.folder, payload.space_id);
    assertCurrent(captured);
    await fs().removeDirectory(source.parent, source.entry);
  });
  return forget(payload);
}
async function showFolder(payload) {
  const captured = stamp(), folder = await folderFor(payload);
  await permission(folder.handle);
  assertCurrent(captured);
  const message = `Current folder: ${folder.name}. This browser saves directly to the folder you selected.`;
  if (typeof toast === 'function') toast(message);
  return { folder: folder.name, browser_folder: folder, message, revealed: true };
}

// Relocation is explicit. Copy first, publish the new handle only after the
// whole tree succeeds; retain the source as recovery instead of deleting it.
async function storagePlan(payload) {
  const parent = payload.parent?.handle || payload.parent;
  if (!parent || parent.kind !== 'directory') throw new Error('Choose a storage folder with the directory picker.');
  await permission(parent);
  const old = await fs().load('home');
  const same = Boolean(old?.handle && await SP.sameHostedHandle(old.handle, parent));
  if (old?.handle && !same && ((await old.handle.resolve(parent)) !== null || (await parent.resolve(old.handle)) !== null)) {
    throw new Error('Choose a location outside the current Space storage folder.');
  }
  let conflict = false;
  if (!same) for await (const entry of parent.entries()) { conflict = true; break; }
  return { parent: { handle: parent, name: parent.name }, root: parent.name, current_root: old?.handle?.name || null,
    source_exists: Boolean(old?.handle && await fs().queryReadWritePermission(old.handle)), same, conflict };
}
async function changeStorage(payload) {
  const prior = state.relocating;
  state.relocating = true;
  try { return await changeStorageNow(payload); }
  finally { state.relocating = prior; }
}
async function changeStorageNow(payload) {
  const captured = stamp(), plan = await storagePlan(payload);
  if (plan.same) return { status: 'unchanged', ...await storageState() };
  if (!['move', 'switch', 'use_existing'].includes(payload.mode)) throw new Error('Choose how to change the Space storage folder.');
  if (plan.conflict && payload.mode !== 'use_existing') return { status: 'conflict', ...plan };
  if (payload.mode === 'move' && !plan.source_exists) throw new Error('Reconnect the current storage folder before moving its Spaces.');
  await SP.flushOutgoingResumeCheckpoint();
  await fs().flushFolderWrites();
  const old = await fs().load('home'), selected = plan.parent.handle;
  const active = await fs().load('active');
  const activePath = old?.handle && active?.handle ? await old.handle.resolve(active.handle) : null;
  if (payload.mode === 'move' && plan.source_exists) {
    const copied = [];
    try {
      for await (const [name, entry] of old.handle.entries()) {
        assertCurrent(captured);
        if (entry.kind === 'directory') {
          const handle = await selected.getDirectoryHandle(name, { create: true });
          copied.push({ parent: selected, name, kind: 'directory' });
          await fs().copyDirectory(entry, handle, [], copied);
        } else {
          if (await fs().fileExists(selected, name)) throw new Error('A file appeared in the storage destination. It was not overwritten.');
          const blob = await fs().readBlob(old.handle, name);
          copied.push({ parent: selected, name, kind: 'file', sha256: await fs().sha256Blob(blob) });
          await fs().writeBlob(selected, name, blob);
        }
      }
    } catch (error) {
      try { await fs().rollbackCopy(copied); }
      catch (_cleanup) { throw new Error('Storage copy failed and an incomplete copy remains in the selected folder. The original is unchanged.'); }
      throw error;
    }
  }
  assertCurrent(captured);
  // Journal handles only, never Space contents. A failed publication retains
  // the old authority and can be repaired without overwriting either tree.
  const originalRecent = await recent();
  await fs().save('storage-change-recovery-v1', { old, selected: plan.parent, active, recent: originalRecent });
  try {
    let replacement = null;
    if (payload.mode === 'move' && activePath?.length === 1) {
      replacement = { ...active, handle: await selected.getDirectoryHandle(activePath[0]) };
    } else if (!activePath) replacement = active;
    const rows = [];
    for (const row of originalRecent) {
      const path = old?.handle ? await old.handle.resolve(row.handle) : null;
      if (!path) rows.push(row);
      else if (payload.mode === 'move' && path.length === 1) rows.push({ ...row, handle: await selected.getDirectoryHandle(path[0]) });
    }
    assertCurrent(captured);
    await fs().saveRecords({ home: { handle: selected, leftover: payload.mode === 'move' ? old?.handle?.name : null }, active: replacement,
      [SP.HOSTED_RECENT_KEY]: rows, 'storage-change-recovery-v1': null });
  } catch (error) {
    throw new Error(`The folders are intact and the original location remains selected: ${error.message}`);
  }
  return { status: 'ok', ...await storageState(), leftover: payload.mode === 'move' ? old?.handle?.name : null, source_retained: payload.mode === 'move' };
}

const RECOVERY_KEY = 'space-import-recovery-v1';
function base64(bytes) {
  let text = '';
  for (let offset = 0; offset < bytes.length; offset += 16384) text += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  return btoa(text);
}
function safePath(path) {
  if (!Array.isArray(path) || !path.length || path.some(part => typeof part !== 'string' ||
      !part || part === '.' || part === '..' || /[\/\\\x00]/.test(part))) throw new Error('The Space export contains an unsafe filename.');
  return path;
}
async function validateBackup(backup) {
  if (backup?.format !== 'wavefinity-space/1' || !Array.isArray(backup.files)) throw new Error('Choose a Wavefinity Space export.');
  const seen = new Set(), blobs = [];
  for (const record of backup.files) {
    const path = safePath(record.path);
    const key = path.map(part => part.toLowerCase()).join('/');
    if (seen.has(key)) throw new Error('The Space export contains duplicate filenames.');
    seen.add(key);
    if (typeof record.base64 !== 'string') throw new Error('The Space export contains unreadable file data.');
    const bytes = Uint8Array.from(atob(record.base64), character => character.charCodeAt(0));
    const blob = new Blob([bytes]);
    if (await fs().sha256Blob(blob) !== record.sha256) throw new Error('The Space export is damaged. No files were imported.');
    blobs.push({ path, blob });
  }
  // A file cannot also be a parent directory, including on case-insensitive
  // filesystems. Reject this before creating any destination entries.
  for (const record of blobs) for (let depth = 1; depth < record.path.length; depth++) {
    if (seen.has(record.path.slice(0, depth).map(part => part.toLowerCase()).join('/'))) throw new Error('The Space export has conflicting file paths.');
  }
  const marker = blobs.find(row => row.path.length === 1 && row.path[0] === FOLDER_METADATA);
  if (!marker) throw new Error('The Space export has no Space metadata.');
  const metadata = JSON.parse(await marker.blob.text());
  const classified = SP.classifyMetadata({ exists: true, data: metadata });
  if (classified.status !== 'space' || classified.needsMigration || !classified.space_id) throw new Error('This Space export requires setup or contains damaged metadata.');
  await values('validate', { space: metadata.space });
  const inventory = blobs.find(row => row.path.length === 1 && row.path[0] === INVENTORY_FILENAME);
  if (inventory) await values('copy-text', { inventory_text: await inventory.blob.text(), name: metadata.space.name,
    space: metadata.space, resume_design: metadata.resume_design });
  return { blobs, metadata };
}

// Explicit recovery API for B13's unsupported-browser import/export controls.
// Return JSON values so the caller can download/upload without a server path.
export async function exportSpace(payload = {}) {
  const captured = stamp();
  if (!payload.folder && !payload.output && !state.browserFolder?.handle) {
    const recovery = await fs().load(RECOVERY_KEY);
    if (!recovery) throw new Error('No saved Space is available to export. Save the current design file instead.');
    assertCurrent(captured);
    return recovery;
  }
  const folder = await folderFor(payload);
  await SP.flushOutgoingResumeCheckpoint();
  return fs().queueFolderWrite(folder.handle, async () => {
    const info = await inspectFolder(folder, payload.space_id);
    if (info.folder_mode !== 'space') throw new Error('Choose a typed Space to export.');
    const files = [];
    const collect = async (handle, prefix = []) => {
      for await (const [name, entry] of handle.entries()) {
        assertCurrent(captured);
        if (entry.kind === 'directory') await collect(entry, [...prefix, name]);
        else {
          const blob = await fs().readBlob(handle, name);
          files.push({ path: [...prefix, name], base64: base64(new Uint8Array(await blob.arrayBuffer())), sha256: await fs().sha256Blob(blob) });
        }
      }
    };
    await collect(folder.handle);
    assertCurrent(captured);
    return { format: 'wavefinity-space/1', files };
  });
}

export async function importSpace(backup, folder = null) {
  const captured = stamp(), { blobs, metadata } = await validateBackup(backup);
  assertCurrent(captured);
  if (!folder?.handle) {
    // Recovery only: this never claims a persistent Space or autosave. The
    // original metadata/ID and every exported byte remain available to export.
    await fs().save(RECOVERY_KEY, backup);
    assertCurrent(captured);
    return { recovery: true, autosave: false, space_id: metadata.space_id, space: metadata.space,
      resume_design: metadata.resume_design ?? null, resume_pending: metadata.resume_pending };
  }
  for (const row of await recent()) if (row.space_id === metadata.space_id && !(await SP.sameHostedHandle(row.handle, folder.handle))) {
    throw new Error('This Space is already remembered in another folder. Use Copy Space for a new identity, or forget the old shortcut before restoring it.');
  }
  await permission(folder.handle);
  await fs().queueFolderWrite(folder.handle, async () => {
    for await (const _entry of folder.handle.entries()) throw new Error('Import needs an empty selected folder. Existing files were not overwritten.');
    const created = [], directories = new Map();
    try {
      for (const record of blobs) {
        assertCurrent(captured);
        let handle = folder.handle;
        let path = '';
        for (const part of record.path.slice(0, -1)) {
          path += '/' + part;
          if (!directories.has(path)) {
            const child = await handle.getDirectoryHandle(part, { create: true });
            created.push({ parent: handle, name: part, kind: 'directory' });
            directories.set(path, child);
          }
          handle = directories.get(path);
        }
        if (await fs().fileExists(handle, record.path.at(-1))) throw new Error('A file appeared in the import destination. It was not overwritten.');
        created.push({ parent: handle, name: record.path.at(-1), kind: 'file', sha256: await fs().sha256Blob(record.blob) });
        await fs().writeBlob(handle, record.path.at(-1), record.blob);
      }
    } catch (error) {
      try { await fs().rollbackCopy(created); }
      catch (_restore) { throw new Error('Import failed and some imported files could not be removed. The recovery export is unchanged; choose a fresh empty folder.'); }
      throw error;
    }
  });
  assertCurrent(captured);
  return { ...await reply(folder), autosave: true };
}

export const ROUTES = new Map([
  ['/api/browse-output-folder', pick],
  ['/api/folder/use', open], ['/api/folder/no-defined-space', noDefinedSpace], ['/api/folder/inventory', inventory],
  ['/api/space/startup', startup], ['/api/space/inspect', inspect], ['/api/space/other-spaces', otherSpaces],
  ['/api/space/open', open], ['/api/space/use-untyped', useUntyped],
  ['/api/space/create', payload => configure(payload, 'create-text')],
  ['/api/space/configure', payload => configure(payload, 'configure-text')],
  ['/api/space/update', payload => configure(payload, 'update-text')],
  ...['create-text', 'configure-text', 'copy-text', 'copy-name'].map(operation => [`/api/space/${operation}`, payload => currentValues(operation, payload)]),
  ['/api/space/defaults', payload => metadataChange(payload, ['keep_bin_defaults', 'bin_defaults', 'part_defaults'])],
  ['/api/space/resume', payload => metadataChange(payload, ['resume_design', 'resume_pending'], true)],
  ['/api/space/no-inventory', payload => inventory({ ...payload, inventory: false })],
  ['/api/space/forget', forget], ['/api/space/copy', copy], ['/api/space/delete', deleteSpace],
  ['/api/space/show-folder', showFolder],
  ['/api/space/warm', async () => { await WFLocalAPI.init(); return { ok: true }; }],
  ['/api/space/storage-state', storageState], ['/api/space/storage-plan', storagePlan], ['/api/space/storage-change', changeStorage],
  ['/api/space/browse-storage-parent', pick],
  ['/api/space/storage-parent', async payload => {
    const plan = await storagePlan(payload);
    if (plan.conflict) return { status: 'conflict', ...plan };
    await fs().save('home', { handle: plan.parent.handle });
    return storageState();
  }],
]);
