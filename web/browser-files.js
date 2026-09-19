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

  const supportsDirectoryPicker = () => typeof window.showDirectoryPicker === "function";

  const requestReadWritePermission = async handle => {
    if (!handle) return false;
    const options = { mode: "readwrite" };
    if (await handle.queryPermission(options) === "granted") return true;
    return (await handle.requestPermission(options)) === "granted";
  };

  const pickDirectory = async () => {
    if (!supportsDirectoryPicker()) return null;
    const handle = await window.showDirectoryPicker({ mode: "readwrite" });
    return (await requestReadWritePermission(handle)) ? handle : null;
  };

  const download = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const writeBlob = async (handle, filename, blob) => {
    if (!handle) return download(blob, filename);
    if (!(await requestReadWritePermission(handle))) throw new Error("Wavefinity needs permission to save in that folder.");
    const file = await handle.getFileHandle(filename, { create: true });
    const writable = await file.createWritable();
    await writable.write(blob);
    await writable.close();
  };

  const writeText = (handle, filename, text) => writeBlob(handle, filename, new Blob([text], { type: "application/json" }));

  const readText = async (handle, filename) => {
    if (!handle || !(await requestReadWritePermission(handle))) return null;
    try {
      return await (await handle.getFileHandle(filename)).getFile().then(file => file.text());
    } catch (error) {
      if (error.name === "NotFoundError") return null;
      throw error;
    }
  };

  const fileExists = async (handle, filename) => {
    if (!handle || !(await requestReadWritePermission(handle))) return false;
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
    if (!handle || !(await requestReadWritePermission(handle))) return [];
    const names = [];
    for await (const [name, entry] of handle.entries()) {
      if (entry.kind === "file") names.push(name);
    }
    return names;
  };

  const removeFile = async (handle, filename) => {
    if (!handle || !(await requestReadWritePermission(handle))) {
      throw new Error("Wavefinity needs permission to update that folder.");
    }
    await handle.removeEntry(filename);
  };

  return { supportsDirectoryPicker, pickDirectory, requestReadWritePermission, writeBlob, writeText, readText, fileExists, listFilenames, removeFile, save, load };
})();
