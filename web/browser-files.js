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

  const save = async (key, value) => {
    const database = await db();
    await new Promise((resolve, reject) => {
      const request = database.transaction(STORE, "readwrite").objectStore(STORE).put(value, key);
      request.onsuccess = resolve;
      request.onerror = () => reject(request.error);
    });
    database.close();
  };

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
    typeof window.showDirectoryPicker === "function";

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
  const pickDirectory = async () => {
    if (!supportsDirectoryPicker()) {
      return { status: "unsupported", handle: null };
    }
    try {
      const handle = await window.showDirectoryPicker({ mode: "readwrite" });
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
    if (!(await requestReadWritePermission(handle))) throw new Error("Wavefinity needs permission to save in that folder.");
    const file = await handle.getFileHandle(filename, { create: true });
    const writable = await file.createWritable();
    await writable.write(blob);
    await writable.close();
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

  return {
    supportsDirectoryPicker, pickDirectory,
    queryReadWritePermission, requestReadWritePermission,
    writeBlob, writeText, readText, fileExists, listFilenames, removeFile,
    save, load,
  };
})();
