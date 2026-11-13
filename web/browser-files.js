"use strict";

// Hosted Wavefinity writes to a folder the person chose in their browser. The
// browser owns that permission and stores the handle; Python never receives a
// pretend client-side path.
window.WFFileSystem = (() => {
  const DB_NAME = "wavefinity-browser-files";
  const STORE = "spaces";

  const db = () => new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  const saveRecords = async records => {
    const database = await db();
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(STORE, "readwrite");
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error || new Error("Browser storage was not saved."));
        const store = transaction.objectStore(STORE);
        try {
          for (const [key, value] of Object.entries(records)) store.put(value, key);
        } catch (error) { transaction.abort(); reject(error); }
      });
    } finally { database.close(); }
  };
  const save = (key, value) => saveRecords({ [key]: value });

  // Handles restored from IndexedDB are different JS objects for the same
  // directory. Resolve their identity before reserving a write slot.
  const folderQueues = [];
  let reservation = Promise.resolve();
  const queueFolderWrite = (handle, task) => {
    const reserve = reservation.then(async () => {
      requireDirectoryHandle(handle);
      let row;
      for (const candidate of folderQueues) {
        if (candidate.handle === handle || await candidate.handle.isSameEntry(handle)) { row = candidate; break; }
      }
      if (!row) { row = { handle, tail: Promise.resolve() }; folderQueues.push(row); }
      const result = row.tail.then(task, task);
      row.tail = result.then(() => {}, () => {});
      return { result };
    });
    reservation = reserve.then(() => {}, () => {});
    return reserve.then(slot => slot.result);
  };
  const flushFolderWrites = () => reservation.then(() => Promise.all(folderQueues.map(row => row.tail)));

  const load = async key => {
    const database = await db();
    const value = await new Promise((resolve, reject) => {
      const request = database.transaction(STORE).objectStore(STORE).get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
    database.close();
    return value;
  };

  // Capability, never an OS or browser name: a browser either exposes a
  // usable writable directory picker in a secure context, or it does not.
  const supportsDirectoryPicker = () =>
    window.isSecureContext &&
    typeof window.showDirectoryPicker === "function" &&
    typeof window.FileSystemDirectoryHandle === "function" &&
    typeof window.FileSystemFileHandle?.prototype?.createWritable === "function";

  // Read-only check. Safe at startup, where there is no user gesture to
  // spend on a permission prompt.
  const queryReadWritePermission = async handle => {
    if (!handle || typeof handle.queryPermission !== "function") return false;
    try {
      return (await handle.queryPermission({ mode: "readwrite" })) === "granted";
    } catch (_error) {
      return false;
    }
  };

  const requestReadWritePermission = async handle => {
    if (!handle) return false;
    if (await queryReadWritePermission(handle)) return true;
    if (typeof handle.requestPermission !== "function") return false;
    try {
      return (await handle.requestPermission({ mode: "readwrite" })) === "granted";
    } catch (error) {
      if (["SecurityError", "NotAllowedError"].includes(error?.name)) return false;
      throw error;
    }
  };

  // Returns a status, never a fabricated folder: "ok", "cancelled",
  // "denied" or "unsupported".
  const pickDirectory = async (options = {}) => {
    if (!supportsDirectoryPicker()) {
      return { status: "unsupported", handle: null };
    }
    try {
      const handle = await window.showDirectoryPicker({ mode: "readwrite", ...options });
      if (
        !handle ||
        handle.kind !== "directory" ||
        typeof handle.getFileHandle !== "function"
      ) {
        return { status: "unsupported", handle: null };
      }
      if (!(await requestReadWritePermission(handle))) {
        return { status: "denied", handle: null };
      }
      return { status: "ok", handle };
    } catch (error) {
      if (error?.name === "AbortError") {
        return { status: "cancelled", handle: null };
      }
      if (["SecurityError", "NotAllowedError"].includes(error?.name)) {
        return { status: "denied", handle: null };
      }
      throw error;
    }
  };

  // Persistent-file primitives fail closed. A missing handle or a lost
  // permission must never be reported as "the file is not there", and a
  // metadata/inventory write must never fall through to a download.
  const requireDirectoryHandle = handle => {
    if (!supportsDirectoryPicker()) throw new Error("This browser cannot save Spaces or autosave folders. Use Windows desktop Chrome/Edge and select the original folder, or import your Space export there.");
    if (!handle) {
      throw new Error("Inventory and Spaces need access to a writable folder.");
    }
    return handle;
  };

  const requireWritableFolder = async handle => {
    requireDirectoryHandle(handle);
    if (!(await requestReadWritePermission(handle))) {
      throw new Error(
        "Wavefinity no longer has permission to read and write that folder. Choose the folder again and allow access.",
      );
    }
  };

  const download = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  // The one deliberate no-handle fallback in this file: ordinary generated
  // design files download when no folder is selected. Persistent Space and
  // inventory writes go through writeText(), which requires a real handle.
  const writeBlob = async (handle, filename, blob) => {
    if (!handle) return download(blob, filename);
    requireDirectoryHandle(handle);
    if (!(await requestReadWritePermission(handle))) throw new Error("Wavefinity needs permission to save in that folder.");
    const file = await handle.getFileHandle(filename, { create: true });
    const writable = await file.createWritable();
    try {
      await writable.write(blob);
      await writable.close();
    } catch (error) {
      try { await writable.abort(); } catch (_abort) { /* Preserve the original failure. */ }
      throw error;
    }
  };

  const writeText = async (handle, filename, text) => {
    requireDirectoryHandle(handle);
    return writeBlob(
      handle,
      filename,
      new Blob([text], { type: "application/json" }),
    );
  };

  const readText = async (handle, filename) => {
    await requireWritableFolder(handle);
    try {
      return await (await handle.getFileHandle(filename)).getFile().then(file => file.text());
    } catch (error) {
      if (error.name === "NotFoundError") return null;
      throw error;
    }
  };

  const fileExists = async (handle, filename) => {
    await requireWritableFolder(handle);
    try {
      await handle.getFileHandle(filename);
      return true;
    } catch (error) {
      if (error.name === "NotFoundError") return false;
      throw error;
    }
  };

  // Hosted inventory migration needs to see, and remove, the old
  // "<folder name> bins.md" - nothing else.
  const listFilenames = async handle => {
    await requireWritableFolder(handle);
    const names = [];
    for await (const [name, entry] of handle.entries()) {
      if (entry.kind === "file") names.push(name);
    }
    return names;
  };

  const removeFile = async (handle, filename) => {
    await requireWritableFolder(handle);
    await handle.removeEntry(filename);
  };

  const copyDirectory = async (source, destination, skipFiles = [], journal = []) => {
    await requireWritableFolder(source);
    await requireWritableFolder(destination);
    for await (const _entry of destination.entries()) {
      throw new Error("The destination folder is not empty. Choose a new folder; existing files were not overwritten.");
    }
    for await (const [name, entry] of source.entries()) {
      if (skipFiles.includes(name)) continue;
      if (entry.kind === "directory") {
        const child = await destination.getDirectoryHandle(name, { create: true });
        journal.push({ parent: destination, name, kind: "directory" });
        await copyDirectory(entry, child, [], journal);
      } else {
        const blob = await readBlob(source, name);
        if (await fileExists(destination, name)) throw new Error("A file appeared in the copy destination. It was not overwritten.");
        journal.push({ parent: destination, name, kind: "file", sha256: await sha256Blob(blob) });
        await writeBlob(destination, name, blob);
      }
    }
    return journal;
  };

  // Delete only our recorded bytes and empty directories during rollback.
  // A file another program changed, or an unexpected extra file, stays put.
  const rollbackCopy = async journal => {
    const empty = await sha256Blob(new Blob([]));
    let incomplete = false;
    for (const row of [...journal].reverse()) {
      try {
        if (row.kind === "file") {
          const actual = await sha256(row.parent, row.name);
          if (actual === null) continue;
          if (actual !== row.sha256 && actual !== empty) { incomplete = true; continue; }
        }
        await row.parent.removeEntry(row.name);
      } catch (error) { if (error.name !== "NotFoundError") incomplete = true; }
    }
    if (incomplete) throw new Error("Some copied files changed or could not be removed. The incomplete copy was retained for recovery.");
  };

  const removeDirectory = async (parent, name) => {
    await requireWritableFolder(parent);
    await parent.removeEntry(name, { recursive: true });
  };

  // Structural-output ownership (Fix 084B): read a file back as a Blob (null if
  // absent) and fingerprint it, so Wavefinity only ever replaces bytes it wrote.
  const readBlob = async (handle, filename) => {
    await requireWritableFolder(handle);
    try {
      return await (await handle.getFileHandle(filename)).getFile();
    } catch (error) {
      if (error.name === "NotFoundError") return null;
      throw error;
    }
  };

  const sha256Blob = async blob => {
    const digest = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
    return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  };

  const sha256 = async (handle, filename) => {
    const blob = await readBlob(handle, filename);
    return blob ? sha256Blob(blob) : null;
  };

  return {
    supportsDirectoryPicker, pickDirectory,
    queryReadWritePermission, requestReadWritePermission,
    writeBlob, writeText, readText, fileExists, listFilenames, removeFile,
    readBlob, sha256, sha256Blob,
    copyDirectory, rollbackCopy, removeDirectory,
    save, saveRecords, load, queueFolderWrite, flushFolderWrites,
  };
})();
