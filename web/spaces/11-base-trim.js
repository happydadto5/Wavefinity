"use strict";

// ---- Surface Base Trim: owned-output lifecycle, current-printer readiness (Fix 095)
//
// The server owns the Base Trim piece plan, signature and, locally, the currentness
// status. Hosted status is recomputed here from the committed browser manifest and
// the real files in the chosen folder - never from a server temp.

SP.baseTrimInfo = { key: "", plan: null, status: null, error: "", serial: 0 };

SP.BASE_TRIM_STATUS_TEXT = {
  current: "Current",
  missing: "Needs save",
  needs_update: "Needs save",
  externally_changed: "Saved file changed outside Wavefinity",
  recovery_error: "Needs recovery",
};

SP.baseTrimSummaryText = () => {
  const info = SP.baseTrimInfo;
  if (info.error) return `Base Trim · ${info.error}`;
  if (info.status && info.status.status === "recovery_error") {
    // (Fix 096 A8) An interrupted save that could not be settled: surface
    // the recovery instructions, never "Needs save".
    return `Base Trim · ${SP.BASE_TRIM_STATUS_TEXT.recovery_error} · ${info.status.message}`;
  }
  if (!info.plan || !info.status) return "";
  const count = Number(info.plan.piece_count);
  const pieces = `${count} ${count === 1 ? "piece" : "pieces"} for current printer`;
  return `Base Trim · ${pieces} · ${SP.BASE_TRIM_STATUS_TEXT[info.status.status] || "Needs save"}`;
};

// ---- hosted Base Trim durable save journal (Fix 096 A8)
//
// Clones the hosted cabinet save journal pattern (Fix 086) under Base Trim's
// own namespace. Before any owned final is replaced, an app-owned journal
// (Space ID, prior and candidate manifests, filenames, backup filenames,
// newly-created filenames) and durable backups are written into the folder
// itself. The next hosted status or save settles the journal first, so an
// interrupted save is idempotent across reload/retry. Cabinet journal keys
// are never used here.
SP.BASE_TRIM_JOURNAL = ".wavefinity-basetrim-journal.json";
SP.BASE_TRIM_BACKUP_PREFIX = ".wavefinity-basetrim-backup-";
SP.BASE_TRIM_BACKUP_NAME = /^\.wavefinity-basetrim-backup-[0-9a-f-]+-\d+\.3mf$/;

SP.baseTrimRecoveryError = message =>
  Object.assign(new Error(`Base Trim recovery is needed: ${message}`), { code: "BASE_TRIM_RECOVERY" });

// A journal this tab is writing right now is a live transaction, not an
// interrupted one: only the save itself (`own`) may settle it.
SP._hostedBaseTrimSaving = false;

// Orphan app-owned backups only, and only when no journal is active.
SP.sweepHostedBaseTrimDebris = async handle => {
  for (const name of await WFFileSystem.listFilenames(handle)) {
    if (SP.BASE_TRIM_BACKUP_NAME.test(name)) {
      try { await WFFileSystem.removeFile(handle, name); } catch (_error) { /* left for the next sweep */ }
    }
  }
};

SP.recoverBaseTrimJournal = async (handle, spaceId, { own = false } = {}) => {
  if (SP._hostedBaseTrimSaving && !own) return "busy";
  const text = await WFFileSystem.readText(handle, SP.BASE_TRIM_JOURNAL);
  if (text === null) {
    await SP.sweepHostedBaseTrimDebris(handle);
    return "none";
  }
  let journal;
  try {
    journal = JSON.parse(text);
    const valid = journal && journal.version === 1 && typeof journal.tx === "string" &&
      typeof journal.space_id === "string" && Array.isArray(journal.files) &&
      journal.candidate_manifest && typeof journal.candidate_manifest === "object" &&
      journal.files.every(file => file && typeof file.name === "string" && typeof file.created === "boolean" &&
        (file.created || (typeof file.backup === "string" && typeof file.original_sha256 === "string")));
    if (!valid) throw new Error("invalid journal");
  } catch (_error) {
    throw SP.baseTrimRecoveryError(`the interrupted-save record in this folder (${SP.BASE_TRIM_JOURNAL}) is damaged. Check the Base Trim files, then delete that file to continue.`);
  }
  if (journal.space_id !== spaceId) {
    throw SP.baseTrimRecoveryError("an unfinished Base Trim save in this folder belongs to a different Space.");
  }
  const { current } = await SP.readMetadata(handle);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== spaceId) {
    throw SP.baseTrimRecoveryError("this folder's Space could not be confirmed.");
  }
  const stored = meta.structural_outputs?.base_trim || null;
  const committed = Boolean(stored) && JSON.stringify(stored) === JSON.stringify(journal.candidate_manifest);
  if (!committed) {
    for (const file of journal.files) {
      if (file.created) {
        await SP.removeIfPresent(handle, file.name);
        continue;
      }
      const backup = await WFFileSystem.readBlob(handle, file.backup);
      if (backup) {
        if ((await WFFileSystem.sha256Blob(backup)) !== file.original_sha256) {
          throw SP.baseTrimRecoveryError(`the backup of ${file.name} is damaged, so the original could not be restored.`);
        }
        await WFFileSystem.writeBlob(handle, file.name, new Blob([await backup.arrayBuffer()]));
      } else if ((await WFFileSystem.sha256(handle, file.name)) !== file.original_sha256) {
        throw SP.baseTrimRecoveryError(`the original ${file.name} could not be restored.`);
      }
    }
  }
  for (const file of journal.files) {
    if (file.backup) await SP.removeIfPresent(handle, file.backup);
  }
  await SP.removeIfPresent(handle, SP.BASE_TRIM_JOURNAL);
  return committed ? "committed" : "rolled_back";
};

SP.hostedBaseTrimStatus = async (plan, signature) => {
  const handle = state.browserFolder?.handle;
  if (!handle) return { status: "missing" };
  if (SP._hostedBaseTrimSaving) return SP.baseTrimInfo.status || { status: "missing" };
  // A journal left by an interrupted save is settled first: committed leftovers
  // are cleaned, anything else is rolled back, before ownership is compared. (Fix 096 A8)
  await SP.recoverBaseTrimJournal(handle, state.activeSpaceId);
  const { current } = await SP.readMetadata(handle);
  const manifest = SP.classifyMetadata(current).structural_outputs?.base_trim;
  const rows = manifest?.pieces;
  if (manifest?.schema !== 1 || !Array.isArray(rows) || !rows.length ||
      rows.some(one => typeof one?.filename !== "string" || typeof one?.sha256 !== "string") ||
      (state.activeSpaceId && manifest.space_id !== state.activeSpaceId)) {
    return { status: "missing" };
  }
  if (manifest.signature !== signature ||
      rows.map(one => one.filename).join("\n") !== plan.filenames.join("\n")) {
    return { status: "needs_update" };
  }
  const changed = [];
  const absent = [];
  for (const piece of rows) {
    const hash = await WFFileSystem.sha256(handle, piece.filename);
    if (hash === null) absent.push(piece.filename);
    else if (hash !== piece.sha256) changed.push(piece.filename);
  }
  if (changed.length) return { status: "externally_changed", changed, absent };
  if (absent.length) return { status: "missing", absent };
  return { status: "current" };
};

SP.refreshBaseTrimSummary = async () => {
  const space = state.activeSpace;
  if (SP.structuralKind() !== "base_trim" || !space) return;
  const hosted = Boolean(state.runtime.hosted);
  const profile = PrinterProfile.current();
  const key = JSON.stringify([space, profile, state.activeSpaceId, SP.baseTrimInfo.serial,
    hosted ? state.browserFolder?.name : state.output]);
  if (SP.baseTrimInfo.key === key) return;
  SP.baseTrimInfo = { ...SP.baseTrimInfo, key, plan: null, status: null, error: "" };
  try {
    const result = await api("/api/space/structural-design", {
      space: clone(space),
      ...(hosted ? { printer_profile: profile } : { output: state.output, space_id: state.activeSpaceId }),
    });
    if (SP.baseTrimInfo.key !== key) return;
    SP.baseTrimInfo.plan = result.plan;
    SP.baseTrimInfo.status = hosted
      ? await SP.hostedBaseTrimStatus(result.plan, result.signature) : result.status;
  } catch (error) {
    if (SP.baseTrimInfo.key !== key) return;
    if (error.code === "BASE_TRIM_RECOVERY") {
      // An interrupted save that cannot be settled is a Base Trim recovery
      // problem, never "changed outside Wavefinity". (Fix 096 A8)
      SP.baseTrimInfo.status = { status: "recovery_error", message: error.message };
    } else {
      SP.baseTrimInfo.error = error.message;
    }
  }
  if (SP.baseTrimInfo.key === key) SP.renderStructuralActions();
};

// Any change to what "current" is measured against re-derives the line next render.
SP.invalidateBaseTrimSummary = () => {
  SP.baseTrimInfo.key = "";
  if (SP.structuralKind() === "base_trim") SP.renderSpaceInfo();
};

SP.fileNames = files => [...new Set((files || []).map(file => String(file?.name || file).split(/[\\/]/).pop()))].join("\n");

// Hosted Save: every piece is downloaded and verified first, only files the prior
// manifest proves are ours (same name, same hash) are replaced, and the manifest is
// committed only after every write succeeded. A durable journal plus on-disk
// backups make an interrupted save recoverable: the next status or save settles
// the journal first, idempotently. (Fix 096 A8)
SP.hostedBaseTrimSave = async (payload, context) => {
  const handle = state.browserFolder.handle;
  const spaceId = state.activeSpaceId;
  // Settle any earlier interrupted save before ownership is compared.
  await SP.recoverBaseTrimJournal(handle, spaceId);
  const exported = await apiSideEffect("/api/space/structural-generate", { ...payload, space_id: spaceId });
  DL.requireSpaceContext(context);
  const candidate = exported.manifest;
  if (!candidate?.pieces?.length) throw new Error("The server did not return the Base Trim files.");
  const { current } = await SP.readMetadata(handle);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== spaceId) {
    throw new Error("This folder is not the Space that was open before. Nothing was changed.");
  }
  const prior = meta.structural_outputs?.base_trim || null;
  const owned = new Map((prior?.schema === 1 && prior.space_id === spaceId && Array.isArray(prior.pieces) ? prior.pieces : [])
    .filter(one => typeof one?.filename === "string" && typeof one?.sha256 === "string")
    .map(one => [one.filename, one.sha256]));

  const blobs = new Map();
  for (const item of exported.files || []) {
    const response = await fetch(item.url);
    if (!response.ok) throw new Error(`Could not download ${item.name}.`);
    blobs.set(item.name, await response.blob());
  }
  for (const piece of candidate.pieces) {
    const blob = blobs.get(piece.filename);
    if (!blob || (await WFFileSystem.sha256Blob(blob)) !== piece.sha256) {
      throw new Error("A Base Trim file did not download correctly. Nothing was changed.");
    }
  }
  for (const piece of candidate.pieces) {
    const existing = await WFFileSystem.sha256(handle, piece.filename);
    if (existing === null) continue;
    // Only a file the prior manifest owns, still unchanged, may be replaced.
    if (owned.get(piece.filename) === undefined || owned.get(piece.filename) !== existing) {
      throw new Error(`${piece.filename} already exists and Wavefinity cannot safely replace it. Rename or move that file, then Save Base Trim again. Nothing was changed.`);
    }
  }
  const txid = crypto.randomUUID();
  const entries = [];
  const backups = [];
  for (const [index, piece] of candidate.pieces.entries()) {
    const old = await WFFileSystem.readBlob(handle, piece.filename);
    if (old) {
      const bytes = new Blob([await old.arrayBuffer()]);
      const backup = `${SP.BASE_TRIM_BACKUP_PREFIX}${txid}-${index}.3mf`;
      entries.push({ name: piece.filename, created: false, backup, original_sha256: await WFFileSystem.sha256Blob(bytes) });
      backups.push([backup, bytes]);
    } else {
      entries.push({ name: piece.filename, created: true });
    }
  }
  SP._hostedBaseTrimSaving = true;
  try {
    // Durable backups first, then the journal that names them, then the installs.
    for (const [name, blob] of backups) await WFFileSystem.writeBlob(handle, name, blob);
    await WFFileSystem.writeText(handle, SP.BASE_TRIM_JOURNAL, JSON.stringify({
      version: 1, tx: txid, space_id: spaceId, prior_manifest: prior, candidate_manifest: candidate, files: entries,
    }));
    for (const piece of candidate.pieces) {
      await WFFileSystem.writeBlob(handle, piece.filename, blobs.get(piece.filename));
    }
    for (const piece of candidate.pieces) {
      if ((await WFFileSystem.sha256(handle, piece.filename)) !== piece.sha256) {
        throw new Error(`${piece.filename} did not save correctly.`);
      }
    }
    DL.requireSpaceContext(context);
    await SP.writeMetadata(handle, "space", null, true, {
      structural_output_updates: { base_trim: candidate },
    }, { preserveSpace: true, expectedSpaceId: spaceId });
  } catch (error) {
    // Roll back from the same durable record a lost tab would have used.
    try { await SP.recoverBaseTrimJournal(handle, spaceId, { own: true }); }
    catch (_recovery) { /* the journal stays; the next status or save settles it */ }
    SP._hostedBaseTrimSaving = false;
    throw error;
  }
  // Committed: only now are the backups, then the journal, cleaned.
  try {
    for (const [name] of backups) await SP.removeIfPresent(handle, name);
    await SP.removeIfPresent(handle, SP.BASE_TRIM_JOURNAL);
  } catch (_cleanup) { /* committed leftovers are cleaned by the next status or save */ }
  SP._hostedBaseTrimSaving = false;
  const warnings = [];
  const desired = new Set(candidate.pieces.map(one => one.filename));
  for (const [name, hash] of owned) {
    if (desired.has(name)) continue;
    try {
      const existing = await WFFileSystem.sha256(handle, name);
      if (existing === null) continue;
      if (existing === hash) await WFFileSystem.removeFile(handle, name);
      else warnings.push(`${name} changed outside Wavefinity; left in place without Base Trim ownership`);
    } catch (_error) {
      warnings.push(`Could not remove old Base Trim file ${name}; remove it manually`);
    }
  }
  return { files: [...desired], warnings };
};

SP.saveBaseTrim = async () => {
  if (SP.structuralBusy || SP.structuralKind() !== "base_trim") return;
  const hosted = Boolean(state.runtime.hosted);
  if (hosted && !state.browserFolder) { toast("Choose a folder before saving files.", true); return; }
  const context = DL.spaceContext();
  const payload = {
    space: clone(state.activeSpace), space_id: state.activeSpaceId,
    ...(hosted ? { printer_profile: PrinterProfile.current() } : { output: state.output }),
  };
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    const saved = hosted
      ? await SP.hostedBaseTrimSave(payload, context)
      : await apiSideEffect("/api/space/structural-generate", payload);
    DL.requireSpaceContext(context);
    const warnings = saved.warnings?.length ? `\n${saved.warnings.join("\n")}` : "";
    toast(`Saved Base Trim${hosted ? "" : ` to ${saved.output || state.output}`}\n${SP.fileNames(saved.files)}${warnings}`, false, 7000);
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast("Base Trim finished for the Space you left. Nothing was changed in the current Space.");
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.baseTrimInfo.serial += 1;
    SP.renderSpaceInfo();
  }
};

// The one Surface print: current-printer Base Trim + placed Not Printed bins + the
// required connectors, handed to the slicer once. Ctrl+Shift+click stays the hidden
// maintainer joint-fit sample (no bins, connectors or status changes).
SP.printSurface = async event => {
  if (SP.structuralBusy || SP.structuralKind() !== "base_trim") return;
  if (state.runtime.hosted) { toast(SP.HOSTED_SURFACE_PRINT_TOOLTIP, true, 6000); return; }
  if (!state.slicer?.available) {
    toast("A slicer prepares 3D-print files for your printer. Open Printer Settings… to choose one.", true, 8000);
    return;
  }
  if (event?.ctrlKey && event?.shiftKey) return SP.runStructural("print", event);
  const context = DL.spaceContext();
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    DL.requireSpaceContext(context);
    if (typeof flushSpaceDesignAutosave === "function" &&
        !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) return;
    DL.requireSpaceContext(context);
    if (!(await DL.save())) return;
    DL.requireSpaceContext(context);
    const result = await apiSideEffect("/api/space/surface-print", {
      output: context.output, space_id: context.spaceId,
      slicer_path: state.slicer?.path || null,
    });
    DL.requireSpaceContext(context);
    DL.adoptBatchResult(result);
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    if (result.partial) toast(result.error || "Surface print stopped before Bambu Studio opened.", true, 10000);
    else toast(`Sent Surface + Bins to ${state.slicer?.name || "the slicer"}!\n${SP.fileNames(result.files)}`, false, 8000);
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast("Surface print belongs to the Space you left. The current Space was not changed.");
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.baseTrimInfo.serial += 1;
    SP.renderSpaceInfo();
  }
};

