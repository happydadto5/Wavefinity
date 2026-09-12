"use strict";

// Spaces - the welcome screen. Each save folder is one space: a drawer, or a
// box (a Bin for Bins case whose inside is the space), with its own inventory
// file. A folder can instead keep no inventory. Picking a folder that is
// neither starts a new space.
//
// Uses the page's globals from app.js ($, $$, api, toast, escapeHtml, fmt,
// number, clone, state, activatePreviewView, syncForm, changedDesign ...) and
// the Layout view's DL / DP.

const SP = { recent: [], setup: null, busy: false, resume: null, ticker: null };

// How long the resume screen waits before carrying on in the space you were
// last in.  Long enough to read and stop, short enough that the common case -
// open the app, keep working where you were - costs nothing.
const SP_RESUME_SECONDS = 10;

const SP_KINDS = {
  drawer: { icon: "🗄️", label: "Drawer" },
  box: { icon: "📦", label: "Box" },
  none: { icon: "📁", label: "No inventory" },
};

const spSame = (a, b) => {
  const tidy = path => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  return tidy(a) === tidy(b);
};

SP.dialog = () => $("#welcome-dialog");

SP.open = async (view = "home", info = null) => {
  try {
    SP.recent = (await api("/api/space/inspect", { output: state.output })).recent || [];
  } catch (error) {
    toast(error.message, true);
  }
  if (view === "setup" && info) SP.showSetup(info); else SP.showHome();
  if (!SP.dialog().open) SP.dialog().showModal();
};

SP.close = () => { if (SP.dialog().open) SP.dialog().close(); };

// ------------------------------------------------------------------ resume

// On launch, a folder that already holds a space does not need the full
// welcome: it needs one question.  Anything the user does - a key, a click,
// another button - stops the clock, so the countdown can only ever act on
// someone who has walked away or is happy to carry on.
SP.launch = async () => {
  let info = null;
  try {
    const data = await api("/api/space/inspect", { output: state.output });
    SP.recent = data.recent || [];
    info = data.space;
  } catch (error) {
    toast(error.message, true);
  }
  if (!info || !info.exists || info.missing || info.no_inventory) return SP.open();
  SP.showResume(info);
  if (!SP.dialog().open) SP.dialog().showModal();
  SP.countdown(info);
};

SP.showResume = info => {
  SP.resume = info;
  $("#welcome-home").hidden = true;
  $("#space-form").hidden = true;
  $("#welcome-resume").hidden = false;
  const space = info.space || {};
  const kind = SP_KINDS[space.kind] || SP_KINDS.drawer;
  $("#welcome-resume-icon").textContent = kind.icon;
  $("#welcome-resume-name").textContent = space.name || info.folder_name;
  $("#welcome-resume-meta").textContent = [
    kind.label,
    space.x ? SP.sizeText([space.x, space.y, space.z]) : "",
  ].filter(Boolean).join(" · ");
  $("#welcome-resume-folder").textContent = info.folder;
  $("#welcome-resume-folder").title = info.folder;
  $("#welcome-resume-continue").focus();
};

SP.stopCountdown = (note = "") => {
  if (SP.ticker) clearInterval(SP.ticker);
  SP.ticker = null;
  const button = $("#welcome-resume-continue");
  if (button) button.textContent = "Keep designing here";
  const line = $("#welcome-resume-countdown");
  if (line) line.textContent = note;
};

SP.countdown = info => {
  SP.stopCountdown();
  let left = SP_RESUME_SECONDS;
  const paint = () => {
    $("#welcome-resume-continue").textContent = `Keep designing here (${left})`;
    $("#welcome-resume-countdown").textContent =
      `Carrying on here in ${left} second${left === 1 ? "" : "s"} - press a key or click to stay on this screen.`;
  };
  paint();
  SP.ticker = setInterval(() => {
    left -= 1;
    if (left > 0) return paint();
    SP.stopCountdown();
    SP.run(() => SP.openSpace(info, { quiet: true }));
  }, 1000);
};

// One request at a time; errors become a toast.
SP.run = async task => {
  if (SP.busy) return;
  SP.busy = true;
  SP.dialog().classList.add("busy");
  try {
    await task();
  } catch (error) {
    toast(error.message, true, 6000);
  } finally {
    SP.busy = false;
    SP.dialog().classList.remove("busy");
  }
};

SP.pickFolder = async () => (await api("/api/browse-output-folder", { current: state.output })).folder || "";
SP.inspect = async folder => (await api("/api/space/inspect", { output: folder })).space;

// Where a chosen folder leads: its space, a no-inventory folder, or a new
// space. `fresh` (New space) sets a no-inventory folder up as a space instead.
SP.route = async (folder, { fresh = false } = {}) => {
  const info = await SP.inspect(folder);
  if (info.missing) throw new Error(`${info.folder} could not be found.`);
  if (info.no_inventory && !fresh) return SP.usePlain(info);
  if (info.exists) {
    if (fresh) toast(`${info.folder_name} already holds a space, so it was opened.`, false, 5000);
    return SP.openSpace(info);
  }
  return SP.open("setup", info);
};

// The Save Location picker hands every chosen folder here.
SP.afterPick = folder => SP.run(() => SP.route(folder));

// ------------------------------------------------------------------ home

SP.showHome = () => {
  SP.stopCountdown();
  $("#welcome-home").hidden = false;
  $("#space-form").hidden = true;
  $("#welcome-resume").hidden = true;
  SP.renderRecent();
};

SP.sizeText = size => (Array.isArray(size) ? `${size.map(fmt).join(" × ")} mm` : "");

SP.renderRecent = () => {
  const list = $("#welcome-recent");
  if (!SP.recent.length) {
    list.innerHTML = `<li class="welcome-empty">No spaces yet. Start with <strong>New space</strong>.</li>`;
    return;
  }
  list.innerHTML = SP.recent.map((one, index) => {
    const kind = SP_KINDS[one.kind] || SP_KINDS.drawer;
    const meta = [kind.label, SP.sizeText(one.size), one.missing ? "folder not found" : ""].filter(Boolean).join(" · ");
    const current = spSame(one.folder, state.output) ? " <em>current</em>" : "";
    return `<li class="welcome-recent-item${one.missing ? " missing" : ""}">
      <button type="button" class="welcome-recent-open" data-index="${index}" title="${escapeHtml(one.folder)}"${one.missing ? " disabled" : ""}>
        <span class="welcome-recent-icon" aria-hidden="true">${kind.icon}</span>
        <span class="welcome-recent-text"><span><strong>${escapeHtml(one.name)}</strong>${current}</span>
          <small>${escapeHtml(meta)}</small><small>${escapeHtml(one.folder)}</small></span>
      </button>
      <button type="button" class="welcome-recent-forget" data-forget="${index}" title="Remove from this list (the folder is not touched)" aria-label="Remove ${escapeHtml(one.name)} from recent spaces">✕</button>
    </li>`;
  }).join("");
};

// ------------------------------------------------------------------ new space

SP.kind = () => $('input[name="space-kind"]:checked')?.value || "drawer";
SP.readSize = () => ["#space-x", "#space-y", "#space-z"].map(sel => number($(sel).value, NaN));
// A B4B inside is whole grid units, as the bin designer snaps it.
SP.snap = mm => {
  const unit = state.catalog?.base_unit || 8;
  return Math.max(unit, Math.round(mm / unit) * unit);
};

SP.showSetup = info => {
  SP.stopCountdown();
  SP.setup = info;
  $("#welcome-home").hidden = true;
  $("#welcome-resume").hidden = true;
  $("#space-form").hidden = false;
  $("#space-folder").textContent = info.folder;
  $("#space-folder").title = info.folder;
  $("#space-name").value = info.folder_name;
  $$('input[name="space-kind"]').forEach(radio => { radio.checked = radio.value === "drawer"; });
  $("#space-error").hidden = true;
  SP.syncSetup();
  $("#space-name").focus();
  $("#space-name").select();
};

SP.syncSetup = () => {
  const kind = SP.kind();
  const plain = kind === "none";
  $("#space-name-row").hidden = plain;
  $("#space-size").hidden = plain;
  const labels = kind === "box"
    ? ["Inside width (X)", "Inside depth (Y)", "Inside height (Z)"]
    : ["Width (X)", "Depth (Y)", "Height (Z)"];
  ["#space-x-label", "#space-y-label", "#space-z-label"].forEach((sel, i) => { $(sel).textContent = labels[i]; });
  $("#space-create").textContent = plain ? "Use this folder" : kind === "box" ? "Create space and design the box" : "Create space";
  SP.noteSize();
};

SP.noteSize = () => {
  const kind = SP.kind();
  const [x, y] = SP.readSize();
  let note = "";
  if (kind === "drawer") note = "Measure the inside of the drawer.";
  if (kind === "box") {
    note = "The box's inside is the space. The largest bin it holds is its inside height.";
    if (x > 0 && y > 0 && (SP.snap(x) !== x || SP.snap(y) !== y)) {
      note = `Box insides come in ${fmt(SP.snap(1))} mm steps, so this one will be ${fmt(SP.snap(x))} × ${fmt(SP.snap(y))} mm inside.`;
    }
  }
  if (kind === "none") note = "Bins are saved here, and no inventory file is kept.";
  $("#space-note").textContent = note;
};

SP.fail = (message, selector) => {
  $("#space-error").textContent = message;
  $("#space-error").hidden = false;
  $(selector)?.focus();
};

SP.create = async () => {
  const info = SP.setup;
  const kind = SP.kind();
  if (kind === "none") return SP.usePlain(info);
  const name = $("#space-name").value.trim();
  let [x, y, z] = SP.readSize();
  if (!name) return SP.fail("Give the space a name.", "#space-name");
  if (![x, y, z].every(value => value > 0)) return SP.fail("Enter the inside width, depth and height in mm.", "#space-x");
  if (kind === "box") [x, y] = [SP.snap(x), SP.snap(y)];
  const data = await api("/api/space/create", { output: info.folder, name, kind, x, y, z });
  SP.recent = data.recent || [];
  await SP.useFolder(data.space.folder, true);
  SP.close();
  if (kind === "box") {
    SP.designBox(data.space.space);
  } else {
    activatePreviewView("drawer");
    toast(`${name} is ready. Design bins, then fit them into it here in the Space tab.`, false, 6000);
  }
};

// ------------------------------------------------------------------ using a folder

// Make the folder the save location. A space logs every bin; a no-inventory
// folder logs none - the existing Keep log switch carries that.
SP.useFolder = async (folder, keepLog) => {
  state.output = folder;
  $("#output-folder").value = folder;
  state.keepLog = keepLog;
  $("#keep-log").checked = keepLog;
  api("/api/preferences", { keep_log: keepLog }).catch(() => {});
  if (typeof DL === "undefined") return;
  // The Layout view holds the old folder's inventory: save it, then re-read.
  if (DL.dirty && DL.layout && DL.output) await DL.save();
  DL.layout = null;
  DL.dirty = false;
  DL.candidates = [];
  DL.selected = null;
  DP.signatures = {};
  if (DL.active) {
    try { await DL.load(); } catch (error) { toast(error.message, true, 7000); }
  }
};

SP.openSpace = async (info, { quiet = false } = {}) => {
  const data = await api("/api/space/open", { output: info.folder });
  SP.recent = data.recent || [];
  await SP.useFolder(info.folder, true);
  SP.close();
  const name = info.space?.name || info.folder_name;
  toast(quiet ? `Carrying on in ${name}.` : `Opened ${name}.`);
};

SP.usePlain = async info => {
  const data = await api("/api/space/no-inventory", { output: info.folder });
  SP.recent = data.recent || [];
  await SP.useFolder(info.folder, false);
  SP.close();
  toast(`Saving bins to ${info.folder_name}. No inventory is kept.`, false, 5000);
};

// A box space goes straight to a Bin for Bins case whose inside is the space.
SP.designBox = space => {
  activatePreviewView("3d");
  if (state.designMutationBusy) {
    toast(`${space.name} is ready. Set Bin type to Bin for Bins to design its case.`, false, 7000);
    return;
  }
  if (designHasChanges() && !window.confirm(`Replace the current design with a Bin for Bins case for ${space.name}?`)) {
    toast(`${space.name} is ready. Set Bin type to Bin for Bins when you want to design its case.`, false, 7000);
    return;
  }
  const previous = clone(state.design);
  clearDraftSelection();
  state.design = clone(state.catalog.defaults.design);
  state.nestPhoto = null;
  state.drafts = {};
  const { box, layout } = state.design;
  Object.assign(box, { x: space.x, y: space.y, z: space.z, easy_clean: false });
  delete box.stack;
  box.b4b = { ...B4B_DEFAULTS, enabled: true };
  layout.features = [];
  layout.mode = "fused";
  state.design.part_name = space.name;
  syncForm();
  readB4BForm(state.design);
  enforceB4BMinimumHeight(state.design, false);
  applyB4BVisibility();
  changedDesign(previous);
  toast(`Designing the box for ${space.name}: ${SP.sizeText([space.x, space.y, space.z])} inside.`, false, 6000);
};

// ------------------------------------------------------------------ wiring

SP.wire = () => {
  $("#spaces-btn").addEventListener("click", () => SP.open());
  $("#welcome-close").addEventListener("click", SP.close);
  $("#welcome-resume-close").addEventListener("click", SP.close);
  $("#welcome-resume-continue").addEventListener("click", () => {
    SP.stopCountdown();
    if (SP.resume) SP.run(() => SP.openSpace(SP.resume));
  });
  $("#welcome-resume-switch").addEventListener("click", SP.showHome);
  // A deliberate action - a key or a click - cancels the auto-continue.  Mouse
  // movement deliberately does not: a cursor resting over the dialog would
  // otherwise stop the clock the user is relying on.
  const stay = () => SP.stopCountdown("Staying on this screen - pick where to work.");
  ["keydown", "pointerdown"].forEach(type =>
    SP.dialog().addEventListener(type, stay, { passive: true })
  );
  SP.dialog().addEventListener("close", () => SP.stopCountdown());
  SP.dialog().addEventListener("click", event => { if (event.target === SP.dialog()) SP.close(); });
  const pickThen = go => () => SP.run(async () => {
    const folder = await SP.pickFolder();
    if (folder) await go(folder);
  });
  $("#welcome-new").addEventListener("click", pickThen(folder => SP.route(folder, { fresh: true })));
  $("#welcome-open").addEventListener("click", pickThen(folder => SP.route(folder)));
  $("#welcome-plain").addEventListener("click", pickThen(async folder => SP.usePlain(await SP.inspect(folder))));
  $("#space-folder-change").addEventListener("click", pickThen(folder => SP.route(folder, { fresh: true })));
  $("#welcome-recent").addEventListener("click", event => {
    const forget = event.target.closest("[data-forget]");
    const open = event.target.closest("[data-index]");
    const one = SP.recent[Number(forget ? forget.dataset.forget : open?.dataset.index)];
    if (!one) return;
    if (forget) {
      SP.run(async () => {
        SP.recent = (await api("/api/space/forget", { output: one.folder })).recent || [];
        SP.renderRecent();
      });
    } else {
      SP.run(() => SP.route(one.folder));
    }
  });
  $$('input[name="space-kind"]').forEach(radio => radio.addEventListener("change", SP.syncSetup));
  ["#space-x", "#space-y"].forEach(sel => $(sel).addEventListener("input", SP.noteSize));
  $("#space-back").addEventListener("click", SP.showHome);
  $("#space-form").addEventListener("submit", event => {
    event.preventDefault();
    SP.run(SP.create);
  });
};

SP.wire();
if (state.ready) SP.launch();
else window.addEventListener("wavefinity:ready", () => SP.launch(), { once: true });
