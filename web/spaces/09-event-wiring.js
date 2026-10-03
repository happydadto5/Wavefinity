"use strict";

SP.wire = () => {
  wireInfoButtons();
  $("#space-cancel-edit")?.addEventListener("click", async () => {
    if (await SP.confirmDiscardSetup()) SP.cancelInlineEdit();
  });
  document.querySelectorAll("#welcome-close, #welcome-resume-close, #space-unsupported-close, #space-type-cards-close, #space-tutorial-close")
    .forEach(el => el?.addEventListener("click", SP.close));
  // A changed cabinet setup asks before it is discarded: X, backdrop, Escape and Back.
  document.getElementById("space-form-close")?.addEventListener("click", SP.requestClose);
  SP.dialog().addEventListener("click", event => { if (event.target === SP.dialog()) SP.requestClose(); });
  SP.dialog().addEventListener("cancel", event => {
    if (SP.setupIsDirty()) { event.preventDefault(); SP.requestClose(); }
  });
  document.getElementById("printer-settings-close")?.addEventListener("click", SP.closePrinterSettings);
  document.getElementById("printer-settings-close-x")?.addEventListener("click", SP.closePrinterSettings);
  const welcomeCreate = document.getElementById("welcome-create");
  if (welcomeCreate) welcomeCreate.addEventListener("click", SP.beginCreateNew);
  const welcomeOpen = document.getElementById("welcome-open");
  if (welcomeOpen) welcomeOpen.addEventListener("click", () => SP.run(SP.openExisting));
  document.querySelectorAll(".welcome-storage-change")
    .forEach(el => el.addEventListener("click", SP.changeStorageParent));
  document.getElementById("space-storage-close")?.addEventListener("click", SP.cancelStorageChange);
  document.getElementById("space-storage-cancel")?.addEventListener("click", SP.cancelStorageChange);
  document.getElementById("space-storage-conflict-cancel")?.addEventListener("click", SP.cancelStorageChange);
  document.getElementById("space-storage-repick")?.addEventListener("click", () => SP.run(SP.pickStorageParent));
  document.getElementById("space-storage-conflict-repick")?.addEventListener("click", () => SP.run(SP.pickStorageParent));
  document.getElementById("space-storage-apply")?.addEventListener("click", () => {
    const chosen = document.querySelector('input[name="space-storage-mode"]:checked');
    SP.applyStorageChange(chosen?.value === "switch" ? "switch" : "move");
  });
  document.getElementById("space-storage-use-existing")?.addEventListener("click", () => SP.applyStorageChange("use_existing"));
  const welcomeDesign = document.getElementById("welcome-design");
  if (welcomeDesign) welcomeDesign.addEventListener("click", () => {
    SP.clearSetupContext();
    SP.run(SP.startUntyped);
  });
  const tutorialOpen = document.getElementById("space-tutorial-open");
  if (tutorialOpen) tutorialOpen.addEventListener("click", SP.showTutorial);
  const tutorialBack = document.getElementById("space-tutorial-back");
  if (tutorialBack) tutorialBack.addEventListener("click", SP.showTypeCards);
  const welcomeResumeContinue = document.getElementById("welcome-resume-continue");
  if (welcomeResumeContinue) welcomeResumeContinue.addEventListener("click", () => SP.run(SP.confirmResume));
  document.getElementById("welcome-resume-create")?.addEventListener("click", SP.beginCreateNew);
  const welcomeResumeSwitch = document.getElementById("welcome-resume-switch");
  if (welcomeResumeSwitch) welcomeResumeSwitch.addEventListener("click", () => {
    // SP.run() calls the task immediately, so showDirectoryPicker() is still
    // reached from the trusted click.
    SP.run(SP.openExisting);
  });
  document.querySelectorAll(".type-card").forEach(el => {
      el.addEventListener("click", () => {
          // A stale inventory candidate may prefill only its own card type;
          // choosing a different type never inherits its dimensions.
          const kind = el.dataset.kind;
          if (kind === "storage_drawers" && SP.configureData) return;
          const candidate = SP.setupPrefillSpace;
          const candidateKind =
            candidate?.kind === "box" ? "portable" : candidate?.kind;
          SP.showSetup(kind, candidateKind === kind ? candidate : null);
      });
  });
  const untypedStart = document.getElementById("space-untyped-start");
  if (untypedStart) untypedStart.addEventListener("click", () => SP.run(SP.startUntyped));
  const spaceBack = document.getElementById("space-back");
  if (spaceBack) spaceBack.addEventListener("click", async () => {
    if (await SP.confirmDiscardSetup()) SP.showTypeCards();
  });
  const spaceForm = document.getElementById("space-form");
  if (spaceForm) {
    // Defensive only: typing/Enter in a field is never permission to create.
    spaceForm.addEventListener("submit", event => event.preventDefault());
  }

  document.getElementById("space-create")
    ?.addEventListener("click", () => SP.run(SP.create));

  document.getElementById("space-save-changes")
    ?.addEventListener("click", () => SP.run(SP.updateSpace));
  const colOpen = document.getElementById("space-collision-open");
  if (colOpen) colOpen.addEventListener("click", () => SP.run(async () => {
    // The collision prompt can be reached by a Space that still needs its
    // one-time setup pass (needs_setup=true) - route into the same explicit
    // setup flow rather than opening it as-is - see Fix 004 Correction 7.B.
    const folder = SP.collisionFolder;
    const data = SP.collisionData;
    SP.collisionFolder = null;
    SP.collisionData = null;
    SP.collisionOrigin = null;
    if (data?.needs_setup) SP.enterSetupFor(folder, data);
    else await SP.afterPick(folder);
  }));
  const colChoose = document.getElementById("space-collision-choose");
  if (colChoose) colChoose.addEventListener("click", () => SP.run(async () => {
    // Route back to whichever flow actually opened this prompt - the
    // untyped flow must never fall into typed SP.create(), which expects a
    // Space form/name/type that was never filled in - see Fix 004
    // Correction 9.A. Transition off the collision prompt onto a stable
    // screen *before* clearing the state it depends on, so a cancelled
    // replacement folder picker never leaves a dead collision prompt on
    // screen with its target already erased - see Fix 004 Correction 10.B.
    const origin = SP.collisionOrigin;
    if (origin === "untyped") SP.showTypeCards();
    else { SP.showOnly("space-form"); SP.showDialog(); }
    SP.collisionFolder = null;
    SP.collisionData = null;
    SP.collisionOrigin = null;
    if (origin === "untyped") await SP.startUntyped();
    else await SP.create();
  }));

  const existingYes = document.getElementById("space-existing-inventory-yes");
  if (existingYes) existingYes.addEventListener("click", () => SP.run(async () => {
    SP.configureData = SP.pendingConfigureFolder;
    SP.pendingConfigureFolder = null;
    await SP.create();
  }));
  const existingNo = document.getElementById("space-existing-inventory-no");
  if (existingNo) existingNo.addEventListener("click", () => SP.run(async () => {
    SP.showOnly("space-form");
    SP.showDialog();
    SP.pendingConfigureFolder = null;
    await SP.create();
  }));

  const confYes = document.getElementById("space-configure-yes");
  if (confYes) confYes.addEventListener("click", SP.configureFolder);
  const confNo = document.getElementById("space-configure-no");
  if (confNo) confNo.addEventListener("click", () => SP.run(SP.useUntypedFolder));
  const confChoose = document.getElementById("space-configure-choose");
  if (confChoose) confChoose.addEventListener("click", () => SP.run(async () => {
    // Transition to a stable screen before clearing the selected target and
    // asking for another folder, so a cancelled picker never leaves the
    // user on a dead configure prompt referring to a cleared folder - see
    // Fix 004 Correction 10.A.
    SP.showHome();
    SP.configureData = null;
    await SP.openExisting();
  }));

  const welcomeRecent = document.getElementById("welcome-recent");
  if (welcomeRecent) welcomeRecent.addEventListener("click", event => {
    const forget = event.target.closest("[data-forget]");
    const open = event.target.closest("[data-index]");
    const one = SP.recent[Number(forget ? forget.dataset.forget : open?.dataset.index)];
    if (!one) return;
    if (forget) SP.run(async () => {
      if (state.runtime.hosted) {
        const kept = SP.recent.filter((_, index) =>
          index !== Number(forget.dataset.forget));
        SP.recent = kept;
        await SP.saveHostedRecent(kept);
      } else {
        SP.recent = (await api("/api/space/forget", {
          space_id: one.space_id || null, output: one.folder,
        })).recent || [];
      }
      SP.renderRecent();
    });
    else SP.run(() => SP.afterPick(
      state.runtime.hosted
        ? { handle: one.handle, name: one.folder_name || one.name }
        : one.folder
    ));
  });
  document.querySelectorAll("[data-other-spaces-list]").forEach(list =>
    list.addEventListener("click", event => {
      const button = event.target.closest("[data-other-index]");
      const one = SP.otherSpaces[Number(button?.dataset.otherIndex)];
      if (one) SP.run(() => SP.afterPick(one.folder));
    }));

  // Live Drawer/Portable readouts while the user types, not only when the
  // setup screen first opens - see Fix 004 Correction 6.G.
  ["drawer-x", "drawer-y", "drawer-z", "surface-x", "surface-y", "portable-x", "portable-y", "portable-z", "pegboard-x", "pegboard-y", "pegboard-holes-x", "pegboard-holes-y"].forEach(id => {
    const input = document.getElementById(id);
    if (input) input.addEventListener("input", SP.updateReadouts);
  });
  ["portable-lid-type", "portable-latch-count", "portable-handle", "portable-stacking", "portable-wall", "portable-base", "portable-lid-snugness", "portable-label-location", "portable-front-label-style"].forEach(id =>
    document.getElementById(id)?.addEventListener("change", SP.updateReadouts));
  ["portable-label-text"].forEach(id => document.getElementById(id)?.addEventListener("input", SP.updateReadouts));
  ["portable-lid-type", "portable-label-location"].forEach(id =>
    document.getElementById(id)?.addEventListener("change", SP.syncStorageBoxForm));
  // Surface: the maximum stays exactly as typed; the readout below shows the
  // resolved field and finished outside size.
  // Changing trim re-resolves the largest field from that same maximum, never
  // from a previously rounded result.
  document.getElementById("surface-trim")?.addEventListener("change", SP.updateReadouts);
  ["pegboard-standard", "pegboard-size-mode"].forEach(id => document.getElementById(id)?.addEventListener("change", SP.updateReadouts));
};

SP.updateReadouts = () => {
    const unit = state.catalog?.base_unit || 8;
    const kind = SP.setupKind;
    if (kind === "drawer") {
        const x = Number(document.getElementById("drawer-x").value);
        const y = Number(document.getElementById("drawer-y").value);
        const z = Number(document.getElementById("drawer-z").value);
        if (x > 0 && y > 0 && z > 0) {
            document.getElementById("drawer-readout").hidden = false;
            document.getElementById("drawer-size-readout").textContent = `${x} × ${y} × ${z} mm`;
            document.getElementById("drawer-capacity-readout").textContent = `${SP.drawerCapacity(x)} × ${SP.drawerCapacity(y)} units`;
        } else {
            document.getElementById("drawer-readout").hidden = true;
        }
    } else if (kind === "surface") {
        const trimKey = document.getElementById("surface-trim").value;
        const resolved = SP.resolveSurface(
            Number(document.getElementById("surface-x").value),
            Number(document.getElementById("surface-y").value),
            trimKey,
        );
        const readout = document.getElementById("surface-readout");
        const interior = document.getElementById("surface-size-readout");
        const trim = document.getElementById("surface-trim-readout");
        const outside = document.getElementById("surface-outside-readout");
        readout.hidden = !resolved.ok;
        if (resolved.ok) {
            interior.textContent = SP.fieldText(resolved.fieldX, resolved.fieldY);
            trim.textContent = `${SP.surfaceTrimLabel(trimKey)} — ${fmt(resolved.trimWidth)} mm`;
            outside.textContent = `${fmt(resolved.outerX)} × ${fmt(resolved.outerY)} mm`;
        }
    } else if (kind === "portable") {
        const x = Number(document.getElementById("portable-x").value);
        const y = Number(document.getElementById("portable-y").value);
        const z = Number(document.getElementById("portable-z").value);
        if (x > 0 && y > 0 && z > 0) {
            document.getElementById("portable-readout").hidden = false;
            const rx = SP.snap(x);
            const ry = SP.snap(y);
            document.getElementById("portable-size-readout").textContent = `${rx/unit} × ${ry/unit} units (${rx} × ${ry} mm)`;
        } else {
            document.getElementById("portable-readout").hidden = true;
        }
        SP.refreshSetupOutside();
    } else if (kind === "pegboard") {
        const mode = document.getElementById("pegboard-size-mode")?.value || "physical";
        const isPhysical = mode === "physical";
        document.getElementById("pegboard-physical-fields").hidden = !isPhysical;
        document.getElementById("pegboard-hole-fields").hidden = mode !== "holes";
        // Fix 060 C: the physical-size help text and the Residual border
        // readout only mean anything in Physical size mode - in Hole/slot
        // count mode the board is derived directly from an exact count and
        // the residual is always 0, so both leak meaningless state.
        const physicalHelp = document.getElementById("pegboard-physical-help");
        if (physicalHelp) physicalHelp.hidden = !isPhysical;
        const borderRow = document.getElementById("pegboard-border-row");
        if (borderRow) borderRow.hidden = !isPhysical;
        const resolved = SP.resolvePegboard();
        const readout = document.getElementById("pegboard-readout");
        readout.hidden = !resolved.ok;
        if (resolved.ok) {
          document.getElementById("pegboard-grid-readout").textContent = `${resolved.holesX} × ${resolved.holesY} positions — ${fmt(resolved.holesX * resolved.standard.pitch_x_mm)} × ${fmt(resolved.holesY * resolved.standard.pitch_y_mm)} mm`;
          document.getElementById("pegboard-border-readout").textContent = `${fmt(resolved.residualX / 2)} mm sides, ${fmt(resolved.residualY / 2)} mm top/bottom`;
        }
    }
};

