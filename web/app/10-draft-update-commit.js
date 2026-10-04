"use strict";

function updateDraftFromFields(event) {
  bumpBoreEpoch();
  const previousConflictDesign = clone(state.design);
  const previousDraftForConflict = clone(state.draft);
  const previousDraftAutoCommit = state.draftAutoCommit;
  const previousDraftTouched = state.draftTouched;
  const previousCanGenerate = state.canGenerate;
  // Any deliberate edit is a strong enough signal to start saving this draft
  // as it goes, even if the app put it up on its own (see state.draftAutoCommit).
  state.draftAutoCommit = true;
  state.draftTouched = true;
  markDraftChanged();
  const one = state.draft;
  const get = key => $(`[data-draft="${key}"]`, $("#draft-fields"))?.value;
  const oldZone = one.zone;
  const oldCx = (oldZone[0] + oldZone[2]) / 2;
  const oldCy = (oldZone[1] + oldZone[3]) / 2;
  const oldWidth = oldZone[2] - oldZone[0];
  const oldDepth = oldZone[3] - oldZone[1];
  const cx = number(get("cx"), oldCx);
  const cy = number(get("cy"), oldCy);
  const isPocket = one.kind === "pocket";
  const wall = isPocket ? number(one.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
  const oldStyle = one.options?.wall_style ?? state.draftResolvedOptions?.wall_style ?? "straight";
  const oldReach = isPocket ? pocketWallReach(wall, oldStyle) : 0;
  let width = Math.max(0.1, number(get("width"), isPocket ? oldWidth - 2 * oldReach : oldWidth));
  let depth = Math.max(0.1, number(get("depth"), isPocket ? oldDepth - 2 * oldReach : oldDepth));
  if (isPocket) {
    width = width + 2 * oldReach;
    depth = depth + 2 * oldReach;
  }
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
  const info = partInfo();
  const changed = event?.currentTarget?.dataset?.draft || "";
  if (["divider", "pocket", "slot"].includes(one.kind) && changed === "option:wall_style") {
    one.options.wall_style = get(changed) === "wavy" ? "wavy" : "straight";
    if (isPocket) {
      const reach = pocketWallReach(wall, one.options.wall_style);
      const insideW = Math.max(0.1, oldWidth - 2 * oldReach);
      const insideD = Math.max(0.1, oldDepth - 2 * oldReach);
      one.zone = [cx - insideW / 2 - reach, cy - insideD / 2 - reach,
        cx + insideW / 2 + reach, cy + insideD / 2 + reach];
    }
  }
  if (info.flags.qty && one.kind !== "divider" && changed === "count") {
    const count = String(get("count") ?? "auto").trim().toLowerCase();
    one.count = one.kind === "steps"
      ? Math.max(1, Math.round(number(count, 3)))
      : (count === "" || count === "auto" ? null : Math.max(1, Math.round(number(count, 1))));
    if (changed === "count" && one.count != null) {
      const autoUnit = event?.currentTarget?.closest("label")?.querySelector(".unit");
      if (autoUnit?.textContent === "Auto") autoUnit.textContent = "";
    }
  }
  if (info.flags.alternate) {
    one.alternate_ends = get("alternate_ends") === "alternate";
  }
  if (info.flags.item) {
    const item = one.item || starterItem();
    const isCradle = one.kind === "cradle";
    // No holder editor names the tool any more; keep whatever is stored so the
    // engine still has a label for its error messages.
    item.name = item.name || "Custom item";
    const previousProfile = item.profile;
    item.profile = isCradle ? "round" : (get("profile") || "round");
    // Leaving a locked hex-bit profile: drop its fixed 6.35 / 0.25 back to
    // ordinary editable defaults rather than carrying them over.
    const leftHexBit = isHexBitProfile(previousProfile) && !isHexBitProfile(item.profile);
    if (!isCradle && isHexBitProfile(item.profile)) {
      // Size, length and fit are fixed for a hex bit - the fields are locked,
      // so take the preset regardless of what the disabled inputs read.
      const preset = HEX_BIT_PROFILES[item.profile];
      item.clearance = preset.clearance;
      item.segments = [{ length: preset.length, diameter: preset.diameter }];
      delete one.options?.angle;   // a hex bit always stands straight up
      delete one.options?.angle_towards;
    } else {
      // A cradle ignores fit slack entirely, so it has no clearance field -
      // keep the stored value at 0 rather than a stale 0.4 nothing reads.
      item.clearance = isCradle ? 0
        : one.kind === "bore" ? 0.25
        : leftHexBit ? 0.4
        : number(get("clearance"), item.clearance ?? 0.4);
      item.segments = [{
        length: number(get("item_length"), item.segments?.[0]?.length || 40),
        diameter: leftHexBit ? 6 : number(get("item_diameter"), item.segments?.[0]?.diameter || 6),
      }];
    }
    one.item = item;
  }
  one.options ||= {};
  if (one.kind === "cradle") {
    delete one.options.floor_gap;
  }
  if (one.kind === "bore") {
    // Only the Angle towards control itself counts as an explicit choice
    // (Fix 078) - syncing it from the DOM on every unrelated bore edit would
    // wrongly "lock in" whatever the select happens to be showing.
    if (changed === "option:angle_towards") {
      const toward = get("option:angle_towards");
      if (toward !== undefined) one.options.angle_towards = toward;
    }
    // Style and sizing choices are words, never numbers.
    if (changed === "option:bore_style") {
      const previousStyle = boreStyleOf(one);
      const resolvedHeight = number(one.options.height ?? state.draftResolvedOptions?.height, NaN);
      const chosen = normalizeBoreStyle(get(changed));
      one.options.bore_style = chosen;
      delete one.options.wall_style;
      // Base - Wavy Walls and both Walls Only styles stand upright.
      if (chosen !== "base_straight") {
        delete one.options.angle;
        delete one.options.angle_towards;
      }
      // Wall Thickness belongs to Walls Only; a Base style returns to its
      // internal default and a Walls Only style to the bin wall.
      delete one.options.wall;
      if (boreWallsOnly(chosen) && !boreWallsOnly(previousStyle)) {
        // Switching to Walls Only sizes the bin to the Bore by default, and
        // seeds Depth from the Base hole depth just left (Fix 078).
        one.options.xy_size_mode = "bin_to_bore";
        const previousDepth = number(one.options.depth ?? state.draftResolvedOptions?.depth, NaN);
        if (Number.isFinite(previousDepth)) one.options.walls_depth = previousDepth;
        delete one.options.depth;
      } else if (!boreWallsOnly(chosen) && boreWallsOnly(previousStyle)) {
        // Walls Only -> Base keeps a cavity that reaches the normal bin floor
        // unless an explicit Depth was set, which carries over exactly.
        const explicitWallsDepth = Object.prototype.hasOwnProperty.call(one.options, "walls_depth");
        const carriedDepth = explicitWallsDepth
          ? number(one.options.walls_depth, resolvedHeight) : resolvedHeight;
        if (Number.isFinite(carriedDepth)) {
          one.options.depth = roundUpHalfMm(carriedDepth);
          if (boreHeightMode(one) !== "bore_to_bin") one.options.height = roundUpHalfMm(resolvedHeight);
        }
        delete one.options.walls_depth;
        if (one.options.xy_size_mode === "bin_to_bore") delete one.options.xy_size_mode;
      }
    }
    if (changed === "option:xy_size_mode") {
      const before = boreXyMode(one);
      const chosen = get(changed);
      one.options.xy_size_mode = chosen;
      if (chosen === "manual" && before !== "manual") {
        // Leaving an automatic mode keeps its current size as the manual Base.
        one.zone = roundFitZoneUpHalfMm(one.zone);
        pinDraftAxis("width");
        pinDraftAxis("depth");
        if (Number.isInteger(state.selected)) state.partZoneLocks[state.selected] = state.pinnedZone;
      } else {
        delete state.pinnedZone.width;
        delete state.pinnedZone.depth;
      }
    }
    if (changed === "option:height_size_mode") {
      const before = boreHeightMode(one);
      const chosen = get(changed);
      one.options.height_size_mode = chosen;
      const resolvedHeight = number(state.draftResolvedOptions?.height, NaN);
      if (chosen === "bore_to_bin") delete one.options.height;
      else if (before === "bore_to_bin" && Number.isFinite(resolvedHeight)) {
        // Leaving "bore to bin" keeps the height it resolved to as the visible number.
        one.options.height = roundUpHalfMm(resolvedHeight);
      }
    }
  }
  if (one.kind === "nest") {
    if (changed === "nest-count") one.count = Math.max(1, Math.min(20, Math.round(number(get("nest-count"), 1))));
    if (changed === "nest-orientation") {
      const angle = number(get("nest-orientation"), NaN);
      if ([0, 90, 180, 270].includes(angle)) one.rotation = angle;
    }
    if (changed === "nest-alternate") one.alternate_ends = event.currentTarget?.checked === true;
    if (changed === "option:repeat_spacing_percent") {
      const spacing = Math.round(number(get("option:repeat_spacing_percent"), NaN));
      if ([-100, -75, -50, -25, 0, 25, 50, 75, 100].includes(spacing)) one.options.repeat_spacing_percent = spacing;
    }
    applyNestAccessOptions(one.options, changed, get);
    // holder_style is a legacy-compatibility marker: absence of it means a
    // true legacy Photo Nest that must keep its exact old geometry. A Nest
    // that has never had one stored must not silently acquire it just
    // because some unrelated field changed - only a deliberate Holder edit
    // (or a Nest that already has one, i.e. every new-format Nest) may
    // create/update it.
    const holderStyleValue = get("option:holder_style");
    if (holderStyleValue !== undefined && (changed === "option:holder_style"
        || Object.prototype.hasOwnProperty.call(one.options, "holder_style"))) {
      one.options.holder_style = holderStyleValue;
    }
    // Switching Holder resets whatever the previous style's advanced/Push
    // Out state was, so a stale push_out never survives a jump to Recessed.
    if (changed === "option:holder_style" && one.options.holder_style === "recessed"
        && one.options.lift_assist === "push_out") {
      one.options.lift_assist = "auto";
    }
    // Only write auto_size when its own checkbox was the thing that changed -
    // it is a three-way stored preference (true/false/legacy-missing), and
    // any other field edit must leave "missing" as missing rather than
    // silently upgrading a legacy design to full Auto-size.
    if (changed === "option:auto_size") {
      const autoSizeBox = $('[data-draft="option:auto_size"]', $("#draft-fields"));
      one.options.auto_size = autoSizeBox?.checked === true;
    }
  }
  // Text carries the only options that are not numbers: what it says, and its
  // placement choice. Read them straight off their own controls.
  if (info.flags.text) {
    const fields = $("#draft-fields");
    const said = $('[data-draft="option:text"]', fields);
    let letteringChanged = false;
    if (said) {
      one.options.text = said.value;
      seedPartNameFromText(one);
      letteringChanged = changed === "option:text" && said.value.trim() !== "";
    }
    const type = get("option:text_type") || "base_inlaid";
    const oldLevel = one.options.level === "rim" ? "rim" : "base";
    const oldRaised = Boolean(one.options.raised);
    const oldRimSide = one.options.level === "rim"
      ? String(one.options.rim_side || "back").toLowerCase() : null;
    const newLevel = type.startsWith("rim_") ? "rim" : "base";
    const newRaised = type.endsWith("raised");
    one.options.level = newLevel;
    one.options.raised = newRaised;
    delete one.options.auto;
    if (newLevel === "rim") {
      one.options.rim_side = get("option:rim_side") || one.options.rim_side || "back";
    } else {
      delete one.options.rim_side;
    }
    const newRimSide = newLevel === "rim"
      ? String(one.options.rim_side || "back").toLowerCase() : null;
    // One ordered sizing-relevant reset, after the new destination is known.
    // A sizing-relevant change re-seeds the Space remembered default (or the
    // product default when the Space has none) and marks retarget so the
    // server refits from the full destination zone - never from the old
    // small derived zone.
    const sizingRelevant =
      letteringChanged ||
      (changed === "option:text_type" &&
        (newLevel !== oldLevel || newRaised !== oldRaised)) ||
      (changed === "option:rim_side" && newLevel === "rim" &&
        newRimSide !== oldRimSide);
    const recoveringFromSub5AutoFit =
      letteringChanged &&
      one.options?.text_v2 === true &&
      Number.isFinite(Number(one.options?.cap_height)) &&
      Number(one.options.cap_height) > 0 &&
      Number(one.options.cap_height) < 5;
    if (sizingRelevant) {
      const remembered = spaceRememberedTextHeight();
      if (recoveringFromSub5AutoFit) {
        // Latest PM rule: a Text that had been auto-fitted below 5 mm may
        // recover upward to 5 mm, but never automatically above 5 mm.
        one.options.cap_height = 5;
      } else if (remembered !== null) {
        one.options.cap_height = remembered;
      } else {
        delete one.options.cap_height;
      }
      one.options.retarget = newLevel;
      delete one.options.text_v2;
    }
    const destination = one.options.level === "rim"
      ? `rim:${one.options.rim_side || "back"}` : "base";
    const occupied = (state.design.layout?.features || []).some((feature, index) => {
      if (index === state.selected || feature.kind !== "text") return false;
      const place = feature.options?.level === "rim"
        ? `rim:${feature.options?.rim_side || "back"}` : "base";
      return place === destination;
    });
    if (occupied) {
      state.design = previousConflictDesign;
      state.draft = previousDraftForConflict;
      state.draftAutoCommit = previousDraftAutoCommit;
      state.draftTouched = previousDraftTouched;
      state.canGenerate = previousCanGenerate;
      syncForm();
      renderDraftFields();
      updateGenerateAvailability();
      toast(`Only one Text can use the ${destination === "base" ? "base" : "same rim side"}. Change Style or remove the other Text.`, true, 6000);
      return;
    }
    syncRimLabelFromFeatures();
    const conflict = newModifierConflict(previousConflictDesign, state.design);
    if (conflict) {
      state.design = previousConflictDesign;
      state.draft = previousDraftForConflict;
      state.draftAutoCommit = previousDraftAutoCommit;
      state.draftTouched = previousDraftTouched;
      state.canGenerate = previousCanGenerate;
      syncForm();
      renderDraftFields();
      updateGenerateAvailability();
      toast(conflict.message, true, 6000);
      return;
    }
  }
  // A Divider's bottom is one construction mode. Translate that visible choice
  // into its established saved options so older designs stay compatible.
  if (one.kind === "divider") {
    const fields = $("#draft-fields");
    const bottomMode = get("option:bottom_mode") || "flat";
    if (bottomMode === "slope") {
      one.options.slope_base = true;
      delete one.options.scoop;
      if (changed === "option:bottom_mode") {
        one.options.bottom_angle = number(state.draftResolvedOptions?.bottom_default_angle, 45);
      }
    } else if (bottomMode === "scoop") {
      one.options.scoop ||= {};
      if (changed === "option:bottom_mode") {
        one.options.scoop.depth = number(state.draftResolvedOptions?.curved_default_depth, 60);
      }
      for (const key of ["slope_base", "bottom_angle", "reverse_bottom", "alternate_bottom", "minimal_bottom", "bottom_supports"]) delete one.options[key];
    } else {
      for (const key of ["slope_base", "bottom_angle", "reverse_bottom", "alternate_bottom", "minimal_bottom", "bottom_supports", "scoop"]) delete one.options[key];
    }
    for (const key of ["alternate_bottom"]) {
      const boxEl = $(`[data-draft="option:${key}"]`, fields);
      if (!boxEl) continue;
      if (boxEl.checked) one.options[key] = true;
      else delete one.options[key];
    }
    if (bottomMode === "slope") {
      if (get("option:slope_construction") === "crossbars") one.options.minimal_bottom = true;
      else {
        delete one.options.minimal_bottom;
        delete one.options.bottom_supports;
      }
    }
    const labelType = get("option:label_type") || "none";
    if (labelType === "none") {
      delete one.options.label_divisions;
      // Keep remembered side and entered text if this label type is restored.
    } else {
      one.options.label_divisions = true;
      one.options.division_level = labelType === "rim" ? "rim" : "base";
      if (labelType === "rim" && !one.options.division_side) one.options.division_side = "back";
    }
  }
  if (changed.startsWith("option:") &&
      !["text", "auto", "raised", "reverse_bottom", "alternate_bottom", "minimal_bottom",
        "slope_base", "bottom_mode", "slope_construction", "label_divisions", "label_type", "division_level", "division_side", "division_labels",
        "level", "rim_side", "text_type",
        "lift_assist", "finger_position", "push_position", "angle_towards",
        "bore_style", "wall_style", "xy_size_mode", "height_size_mode", "holder_style", "auto_size", "repeat_spacing_percent"]
        .includes(changed.slice("option:".length))) {
    const key = changed.slice("option:".length);
    const option = info.fields.find(entry => entry.key === key);
    const previousGridCount = info.kind === "divider" && (key === "count_x" || key === "count_y")
      ? Math.max(0, Math.round(number(one.options?.[key], 0))) : null;
    const raw = String(get(changed) ?? "").trim();
    if (raw === "") delete one.options[key];
    else {
      let value = number(
        raw,
        one.options[key] ?? state.draftResolvedOptions?.[key] ?? number(option?.default),
      );
      // Bore geometry stores lean away from vertical. The user sees the more
      // natural absolute "Bore angle": 90 is straight up and down. Only a
      // committed (change/blur/Enter) out-of-range value is reported - typing
      // itself is never interrupted (Fix 078).
      if (info.kind === "bore" && key === "angle") {
        const previousCanonicalAngle = number(one.options.angle, 0);
        const displayedAngle = Math.min(90, Math.max(20, value));
        if (event?.type === "change" && Math.abs(displayedAngle - value) > 1e-9) {
          toast(`Bore angle must be between 20° and 90°; using ${fmt(displayedAngle)}°.`, true, 4500);
        }
        value = 90 - displayedAngle;
        // A first transition from upright to angled with no explicit
        // direction chosen yet materializes the default (Fix 078); a later
        // manual choice always wins from then on.
        if (previousCanonicalAngle <= 1e-9 && value > 1e-9 &&
            !Object.prototype.hasOwnProperty.call(one.options, "angle_towards")) {
          one.options.angle_towards = boreDefaultAngleDirection(state.design);
        }
      }
      // A bore's grid counts are whole numbers.
      if (info.kind === "bore" && (key === "columns" || key === "rows")) {
        value = Math.max(1, Math.round(value));
        const autoUnit = event?.currentTarget?.closest("label")?.querySelector(".unit");
        if (autoUnit?.textContent === "Auto") autoUnit.textContent = "";
      }
      // A grid divider's wall counts are whole numbers, zero or more.
      if (info.kind === "divider" && (key === "count_x" || key === "count_y")) {
        value = Math.max(0, Math.round(value));
      }
      if (info.kind === "cradle" && key === "spacing") value = Math.max(0, value);
      one.options[key] = value;
    }
    if (info.kind === "divider" && key === "thickness") {
      widenDividerFootprint(one);
    }
    // Once either grid quantity is set, the divider is a grid: pin both
    // quantities and drop the old single-direction count so nothing double-builds.
    // An older Divider may have only its one-axis count. Its first grid edit
    // begins at one wall on the other axis rather than silently replacing it.
    if (info.kind === "divider" && (key === "count_x" || key === "count_y")) {
      const otherKey = key === "count_x" ? "count_y" : "count_x";
      if (!Object.prototype.hasOwnProperty.call(one.options, otherKey)) {
        one.options[otherKey] = 1;
      }
      if ("count_x" in one.options || "count_y" in one.options) {
        one.options.count_x = Math.max(0, Math.round(number(one.options.count_x, 0)));
        one.options.count_y = Math.max(0, Math.round(number(one.options.count_y, 0)));
        one.count = null;
      }
      const nextGridCount = Math.max(0, Math.round(number(one.options[key], 0)));
      if (previousGridCount !== nextGridCount && one.options.compartment_spans?.length) {
        delete one.options.compartment_spans;
        state.dividerSegmentHover = null;
        toast("Custom compartment merges reset because the divider grid changed.");
      }
    }
    if (info.kind === "pocket" && key === "wall") {
      // Use the live pre-edit wall/reach already captured at the top of this
      // event (`wall`/`oldStyle`/`oldReach`), never the async
      // draftResolvedOptions - that can still lag the live draft while a
      // prior 220 ms preview is in flight, which would subtract the wrong
      // prior reach on rapid edits and drift the inside Width/Length.
      const newWall = number(one.options.wall, 1.6);
      const nextReach = pocketWallReach(newWall, oldStyle);
      const innerW = Math.max(0.1, oldWidth - 2 * oldReach);
      const innerD = Math.max(0.1, oldDepth - 2 * oldReach);
      const newW = innerW + 2 * nextReach;
      const newD = innerD + 2 * nextReach;
      one.zone = [cx - newW / 2, cy - newD / 2, cx + newW / 2, cy + newD / 2];
    }
    keepCutBelowHeight(one, key);
    if (info.kind === "bore" && key === "angle" && !("wall" in (one.options || {}))) {
      // A leaned bore defaults to a thicker wall (engine: BORE_TILTED_WALL);
      // reflect that in the field right away when Wall hasn't been hand-set.
      const wallField = $('[data-draft="option:wall"]', $("#draft-fields"));
      if (wallField) {
        const nextWall = number(one.options.angle, 0) > 0 ? "3" : "1.6";
        if (wallField.value !== nextWall) { wallField.value = nextWall; flashField(wallField); }
      }
    }
    if (one.kind === "nest" && key === "cavity_depth" && raw !== "") {
      // A hand-typed cavity depth means Manual; it stops following Tool
      // thickness until Reset to 60% is pressed.
      one.options.cavity_depth_mode = "manual";
    }
    // The trace may already be done and waiting only on this measurement.
    if (one.kind === "nest" && key === "tool_thickness" && state.nestTraceResult
        && _nestMeasuredThickness(one.options) != null) {
      finishPhotoNestIfReady();
    }
  }
  if (one.kind === "cradle" && (
    changed === "count" || changed === "item_length" || changed === "item_diameter" ||
    changed === "alternate_ends" || changed === "option:spacing" ||
    changed === "option:end_margin" || changed === "option:run_offset"
  )) sizeCradleToItem(one);
  // Any hole parameter that moves the grid's footprint - the X / Y counts, the
  // hole size, the wall between holes, or the lean that adds sideways reach -
  // re-fits the Base block to that grid. Runs before the profile re-render
  // below so the refreshed Width / Length fields show the new size.
  if (one.kind === "bore" && (
    changed === "option:columns" || changed === "option:rows" ||
    changed === "option:depth" || changed === "option:wall" ||
    changed === "option:angle" || changed === "item_diameter" ||
    changed === "clearance" || changed === "profile" || changed === "along" ||
    changed === "option:angle_towards" ||
    changed === "option:bore_style" || changed === "option:xy_size_mode" ||
    changed === "option:height_size_mode"
  )) sizeBoreToGrid(one);
  if (one.kind === "bore" && (changed === "option:bore_style" ||
      changed === "option:xy_size_mode" || changed === "option:height_size_mode")) {
    renderDraftFields();
  }
  // The peg row and the slot bank track their own contents the same way the
  // bore base tracks its grid: change the count, peg size, gap, slot pitch or
  // lean and the zone re-fits (grow or shrink) on the driven axis.
  if (one.kind === "post" && (
    changed === "count" || changed === "option:diameter" ||
    changed === "option:spacing" || changed === "along"
  )) sizePostToRow(one);
  if (one.kind === "slot" && (
    changed === "count" || changed === "option:thickness" ||
    changed === "option:wall" || changed === "option:angle" || changed === "along" ||
    changed === "option:wall_style"
  )) sizeSlotToBank(one);
  // A hand-typed Base Width / Length pins that axis: from now on the contents
  // sizers only ever grow it to fit, never shrink or overwrite the number.
  if (info.flags.size && (changed === "width" || changed === "depth")) {
    pinDraftAxis(changed);
    if (Number.isInteger(state.selected)) state.partZoneLocks[state.selected] = state.pinnedZone;
  }
  // Changing End layout swaps the field beneath Runs along between
  // "From ends" and "Offset from center".
  if (changed === "alternate_ends") renderDraftFields();
  // Switching a bore's profile swaps which fields show (locked hex-bit size,
  // the Angle field for round/square only).
  if (changed === "profile" && one.kind === "bore") renderDraftFields();
  // The dependent "Angle towards" control only re-renders once the Bore angle
  // is committed (change/blur/Enter), never on a raw keystroke, so typing a
  // replacement value is never interrupted mid-edit (Fix 078).
  if (changed === "option:angle" && one.kind === "bore" && event?.type === "change") renderDraftFields();
  if ((changed === "option:lift_assist" || changed === "option:holder_style") && one.kind === "nest") renderDraftFields();
  if (changed === "option:text_type") renderDraftFields();
  if (one.kind === "divider" && (
    changed === "option:bottom_mode" || changed === "option:slope_construction" || changed === "option:label_type" ||
    changed === "option:division_level" || changed === "count" ||
    changed === "option:count_x" || changed === "option:count_y"
  )) renderDraftFields();
  if (one.kind === "post" && changed === "count") renderDraftFields();
  updateSelectionButtons();
  renderLayout2D();
  refreshDraftSoon();
}

const refreshDraftSoon = debounce(refreshDraft, 220);

async function refreshDraft() {
  if (!state.draft) return;
  if (state.draft.kind === "nest" && !state.draft.contour) {
    $("#draft-status").textContent = "Upload one part photo to create the cavity outline.";
    $("#draft-status").classList.remove("error");
    return await refreshPreview();
  }
  // Fix 082 H: blank Text is inert - no fit error, no commit, no fake
  // lettering in the preview. The existing valid bin keeps showing as-is.
  if (isBlankTextDraft(state.draft)) {
    ++state.draftRequest;
    $("#draft-status").textContent = "Type the words this Text should say.";
    $("#draft-status").classList.remove("error");
    state.fitError = false;
    return await refreshPreview();
  }
  // A divider always splits the whole bin, so keep its footprint pinned to
  // the usable inside - re-stretched here every rebuild, which is what makes
  // the walls re-space evenly after the bin is resized (or a wall lean is
  // added, which needs more room between centres). Matches how default_feature
  // first lays a divider out. Its run axis reaches past this rectangle to the
  // wavy wall on its own; this only sets the axis the walls divide.
  if (state.draft.kind === "divider") {
    const [insideX, insideY] = dividerLayoutExtent(state.design.box);
    state.draft.zone = [-insideX / 2, -insideY / 2, insideX / 2, insideY / 2];
  }
  applyBoreSizing(state.draft);
  bumpBoreEpoch();
  const request = ++state.draftRequest;
  updateReferenceAddAvailability();
  if (state.draft.kind === "nest") {
    $("#draft-status").textContent = "Resizing bin around cavity…";
    if (state.draftAutoCommit && !(await autoCommitDraft(request))) {
      if (request !== state.draftRequest) return;
      return await refreshPreview();
    }
    if (request !== state.draftRequest) return;
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    return await refreshPreview();
  }
  $("#draft-status").textContent = "Rebuilding…";
  try {
    const index = draftCommitIndex();
    const result = await api("/api/feature/draft", {
      design: state.design, feature: state.draft,
      ...(index === false ? {} : { index }),
      client_id: previewClientId, generation: request,
    });
    if (request !== state.draftRequest) return;
    if (result.superseded) throw new Error("Current draft was unexpectedly superseded. Try again.");
    const draft = state.draft;
    const textCap = Number(result.resolved_options?.cap_height ?? result.feature?.options?.cap_height);
    if (!(await allowSmallTextEdit(textCap, request, draft))) {
      if (request !== state.draftRequest) return;
      $("#draft-status").textContent = "Text needs to be smaller than 5 mm to fit here.";
      $("#draft-status").classList.remove("error");
      return await refreshPreview();
    }
    if (request !== state.draftRequest) return;
    state.draftResolvedOptions = result.resolved_options || {};
    state.referenceResolutionRequest = request;
    if (state.draft.kind === "text" && result.feature) {
      if (Array.isArray(result.feature.zone)) state.draft.zone = result.feature.zone.slice();
      state.draft.options.text_v2 = true;
      if (state.draft.options.cap_height == null || state.draft.options.cap_height === "") {
        state.draft.options.cap_height = result.feature.options?.cap_height;
      }
      const heightInput = $('[data-draft="option:cap_height"]', $("#draft-fields"));
      if (heightInput && heightInput !== document.activeElement) {
        heightInput.value = String(Math.floor(number(
          result.resolved_options?.cap_height ?? result.feature.options?.cap_height, 15)));
      }
      if (state.draft.options.retarget) {
        delete state.draft.options.retarget;
        // Adopt the effective fitted cap first: for rim Text the feature's
        // own cap_height is still the requested (remembered) height.
        const effectiveCap =
          result.resolved_options?.cap_height ?? result.feature.options?.cap_height;
        if (effectiveCap !== undefined) {
          state.draft.options.cap_height = effectiveCap;
        }
        renderDraftFields();
      }
    }
    // The server's usable layout area is the authority for "bore to bin".
    if (state.draft.kind === "bore" && boreXyMode(state.draft) === "bore_to_bin"
        && !boreWallsOnly(boreStyleOf(state.draft))
        && Array.isArray(result.feature?.zone)) {
      state.draft.zone = result.feature.zone;
    }
    const info = partInfo();
    // The resolver now has the real item depth and lean. Re-size before saving
    // so Base always reflects the actual hole grid, not a stale preview size.
    if (info.kind === "bore") sizeBoreToGrid(state.draft);
    for (const option of info.fields) {
      if (Object.prototype.hasOwnProperty.call(state.draft.options || {}, option.key)) continue;
      const input = $(`[data-draft="option:${option.key}"]`, $("#draft-fields"));
      // Don't overwrite a field the user is still typing in - clearing it to
      // retype briefly drops the key from options, and stomping the auto value
      // back in mid-edit is exactly what makes a 16->20 change snap back to 16.
      if (input && input === document.activeElement) continue;
      if (input && option.type !== "enum"
          && Object.prototype.hasOwnProperty.call(state.draftResolvedOptions, option.key)) {
        const value = state.draftResolvedOptions[option.key];
        const next = fmt(info.kind === "bore" && option.key === "angle" ? 90 - number(value, 0)
          : info.kind === "bore" ? boreDerivedDimension(option.key, value) : value);
        if (input.value !== next) {
          input.value = next;
          flashField(input);
        }
      }
    }
    if (info.flags.qty && state.draft.count == null) {
      const input = $('[data-draft="count"]', $("#draft-fields"));
      const next = String(resolvedDraftCount(state.draft));
      if (input && input.value !== next) {
        input.value = next;
        flashField(input);
      }
    }
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    const committed = !state.draftAutoCommit || await autoCommitDraft(request);
    if (request !== state.draftRequest) return;
    if (committed) updateReferenceAddAvailability();
    // "Auto size bin to bore" (Width / Length or Height) keeps the bin fitted to
    // this Bore after every edit.
    if (request === state.draftRequest && await reconcileBoreBin(result)) return;
  } catch (error) {
    if (request !== state.draftRequest) return;
    // A part whose contents outgrew the bin: grow the bin around it instead of
    // stopping at the error, so "put 10 x 10 holes in a stock bin" (or a longer
    // tool, more pegs, more slots) just resizes the bin the way the "Grow the
    // bin" button would. Guarded so the expand's own rebuild can't loop back in.
    const outgrewBin = new RegExp(
      "reaches outside the bin|bores need|posts need|slots? need|zone is too small" +
      "|the zone (only )?runs|mm long but the zone|layout area|does not fit in|overlap|tool reaches the side",
      "i",
    ).test(error.message || "");
    const growKinds = new Set(["bore", "post", "slot", "cradle", "pocket", "steps"]);
    // A Bore-angle/direction edit owns its own OK/Cancel growth confirmation
    // (Fix 078); this generic silent auto-grow must not preempt it.
    if (growKinds.has(state.draft?.kind) && outgrewBin && !state.autoGrowingBin && !state.boreAngleGrowthPending) {
      state.autoGrowingBin = true;
      try {
        // A Bore that sizes the bin around itself lands on the smallest fit, so
        // the bin shrinks as well as grows to meet it.
        await autoExpandBin({
          keepDraft: true,
          fit: state.draft.kind === "bore" && boreXyMode(state.draft) === "bin_to_bore",
        });
      } finally {
        state.autoGrowingBin = false;
        flushBoreReconcile();
      }
      return;
    }
    $("#draft-status").textContent = friendlyError(error);
    $("#draft-status").classList.add("error");
    state.fitError = true;
    updateAutoExpandButton();
  }
  if (request === state.draftRequest) return await refreshPreview();
}

// Anything that is only a size - "8", "12mm" - names a compartment, not the
// part, so it never becomes the filename.
const SIZE_LIKE_TEXT = /^\s*\d+(\.\d+)?\s*(mm)?\s*$/i;

// The first real piece of lettering fills in a blank Part Name, once. After
// that the two are independent: renaming either never touches the other, so a
// bin can say "M3" on the floor and still save as "Driver rack".
function seedPartNameFromLabel(said) {
  const partInput = $("#part-name");
  if (!partInput) return;
  if (partInput.value.trim() !== "" && document.activeElement === partInput) return;
  const tidy = String(said ?? "").trim();
  if (!tidy || SIZE_LIKE_TEXT.test(tidy)) return;
  partInput.value = tidy;
  if (state.design) state.design.part_name = tidy;
}

// "Real" means the user typed it. A text part starts life blank (Fix 082 H),
// so any lettering it now carries is something the user actually said.
function seedPartNameFromText(one) {
  if (!one || one.kind !== "text") return;
  const said = String(one.options?.text ?? "").trim();
  if (said === String(state.draftStartingText ?? "").trim()) return;
  seedPartNameFromLabel(said);
}

// Where /api/feature/apply should land the current draft:
//   number -> update that already-placed support in place
//   null   -> append it as a brand-new support (a fresh palette draft only)
//   false  -> don't commit: the canvas selection was cleared while editing a
//             placed support, and appending would duplicate it
function draftCommitIndex() {
  if (state.selected !== null) return state.selected;
  if (state.draftIsNew) return null;
  if (Number.isInteger(state.draftSourceIndex) &&
      state.draftSourceIndex < state.design.layout.features.length) {
    return state.draftSourceIndex;
  }
  return false;
}

// Saves the draft into the design as its own feature (or updates it in
// place if it's already one) - the "auto add" half of the workflow: once a
// draft is armed (state.draftAutoCommit), every valid edit lands here
// instead of waiting for an explicit button click. Normal success stays
// silent so it never interrupts active typing; an automatic correction is
// explained once, and a failure (e.g. overlap, which the
// single-feature check above can't see) just shows in draft-status like any
// other validation error.
async function autoCommitDraft(request) {
  if (state.draft?.kind === "nest" && !state.draft.contour) return false;
  if (isBlankTextDraft(state.draft)) return false;
  const index = draftCommitIndex();
  if (index === false) return false;   // stale edit - don't append a duplicate
  if (!state.draftIsNew && Number.isInteger(index) &&
      JSON.stringify(state.design.layout.features[index]) === JSON.stringify(state.draft)) {
    state.draftTouched = false;
    return true;
  }
  try {
    const wasNew = state.draftIsNew;
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/apply", { design: state.design, feature: state.draft, index });
    if (request !== state.draftRequest) return;
    state.design = result.design;
    seedPartNameFromText(state.draft);
    noteCommittedDesignChange(previousDesign);
    state.draftIsNew = false;
    state.draftTouched = false;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    if (state.selected === null && wasNew) state.selected = result.selected;
    // Saved support zones snap to the grid. Without this sync the preview
    // draws an almost-identical draft over the saved support, which is most
    // noticeable after changing a cradle row from one tool to two.
    if (state.selected !== null && state.design.layout.features[state.selected]) {
      state.draft = clone(state.design.layout.features[state.selected]);
    }
    if (state.draft?.kind === "nest") syncForm();
    for (const warning of result.warnings || []) toast(warning, false, 6500);
    renderPlaced();
    updateSelectionButtons();
    if (wasNew && state.draft?.kind !== "text") await maybePromptSurfaceObjectHeight();
    return true;
  } catch (error) {
    if (request !== state.draftRequest) return;
    $("#draft-status").textContent = friendlyError(error);
    $("#draft-status").classList.add("error");
    return false;
  }
}

async function commitVisibleDraft({ previewAfterCommit = true } = {}) {
  if (!state.draft) return false;
  if (state.draft?.kind === "nest" && !state.draft.contour) return false;
  if (isBlankTextDraft(state.draft)) return false;
  const index = draftCommitIndex();
  if (index === false) return false;
  if (Number.isInteger(index) &&
      JSON.stringify(state.design.layout.features[index]) === JSON.stringify(state.draft)) {
    return false;
  }
  if (state.draft.kind === "text" &&
      state.smallTextApprovedDraftRequest !== state.draftRequest) {
    const request = state.draftRequest;
    const draftAtCheck = state.draft;
    const checked = await api("/api/feature/draft", {
      design: state.design, feature: draftAtCheck, index,
    });
    if (request !== state.draftRequest || state.draft !== draftAtCheck) {
      throw new Error("The Text changed while it was being saved. Try again.");
    }
    const cap = Number(checked.resolved_options?.cap_height ?? checked.feature?.options?.cap_height);
    await allowSmallTextEdit(cap, request, draftAtCheck);
    if (request !== state.draftRequest || state.draft !== draftAtCheck) {
      throw new Error("The Text changed while it was being saved. Try again.");
    }
    if ((state.draft.options.cap_height == null || state.draft.options.cap_height === "") &&
        checked.feature?.options?.cap_height != null) {
      state.draft.options.cap_height = checked.feature.options.cap_height;
      state.draft.options.text_v2 = true;
    }
  }
  const draft = state.draft;
  const snapshot = JSON.stringify(draft);
  const previousDesign = clone(state.design);
  state.draftRequest += 1;
  const committed = await api(state.referenceEditPending ? "/api/feature/reference" : "/api/feature/apply", {
    design: state.design, feature: draft, index,
  });
  if (state.draft !== draft || JSON.stringify(draft) !== snapshot) {
    throw new Error("The interior part changed while it was being saved. Try again.");
  }
  state.design = committed.design;
  // A deferred final preview must not leave an older in-flight preview able
  // to adopt its pre-commit design while the transition is still in progress.
  if (!previewAfterCommit) invalidatePendingPreview();
  seedPartNameFromText(draft);
  noteCommittedDesignChange(previousDesign);
  state.draftIsNew = false;
  state.draftTouched = false;
  state.referenceEditPending = false;
  state.selected = committed.selected;
  if (Number.isInteger(committed.selected)) {
    state.draftSourceIndex = committed.selected;
    const saved = state.design.layout.features[committed.selected];
    if (saved) state.draft = clone(saved);
  }
  state.draftResolvedOptions = {};
  if (state.draft?.kind === "nest") syncForm();
  for (const warning of committed.warnings || []) toast(warning, false, 6500);
  renderDraftFields();
  renderPlaced();
  updateSelectionButtons();
  if (previewAfterCommit && typedSpaceOrdinaryBin()) refreshPreview();
  return true;
}

// True when the open draft holds work that switching parts would throw away:
// a new part the user has actually started, or edits to a placed part that
// haven't been saved back yet. An untouched suggestion the app put up on its
// own counts as nothing to lose.
function draftNeedsSaving() {
  if (!state.draft) return false;
  // A Text draft with no words can never be committed (Fix 082 H), so
  // whatever the user typed and deleted while it was open is not work to
  // lose - switching away from it silently is fine.
  if (isBlankTextDraft(state.draft)) return false;
  const index = draftCommitIndex();
  if (Number.isInteger(index)) {
    return JSON.stringify(state.design.layout.features[index]) !== JSON.stringify(state.draft);
  }
  // index is null (brand-new) or false (its row was cleared underneath it).
  return state.draftTouched === true;
}

// Gate every "switch to a different interior part" path. Returns true if the
// caller may go ahead and replace the draft, false if the user chose to stay
// and keep editing. Edits are auto-saved cleanly when valid; only an edit
// that cannot be saved prompts the user to discard or keep editing.
async function guardDraftSwitch({ previewAfterCommit = true } = {}) {
  if (!draftNeedsSaving()) return true;
  try {
    state.draftAutoCommit = true;
    await commitVisibleDraft({ previewAfterCommit });
    return true;
  } catch (error) {
    return promptDraftConflict(error.message);
  }
}

// A transition owns the preview after saving the old draft. If it exits before
// starting that owner, restore the committed state's preview exactly once.
let fullPreviewStarts = 0;
async function deferredDraftSwitch() {
  const priorDesign = state.design;
  const proceed = await guardDraftSwitch({ previewAfterCommit: false });
  const committed = state.design !== priorDesign;
  const ownerAtReturn = fullPreviewStarts;
  let finished = false;
  let claimedDraft = false;
  return {
    proceed, committed,
    claimDraft(promise) {
      if (committed) {
        claimedDraft = true;
        Promise.resolve(promise).then(
          () => { if (fullPreviewStarts === ownerAtReturn) refreshPreview(); },
          () => { if (fullPreviewStarts === ownerAtReturn) refreshPreview(); },
        );
      }
      return promise;
    },
    finish() {
      if (finished) return;
      finished = true;
      if (committed && !claimedDraft && fullPreviewStarts === ownerAtReturn) refreshPreview();
    },
  };
}

async function withDeferredDraftSwitch(action, refused = undefined) {
  const guard = await deferredDraftSwitch();
  try {
    if (!guard.proceed) return refused;
    return await action(guard);
  } finally {
    guard.finish();
  }
}

// The "discard this change?" dialog shown when an edit cannot be saved cleanly.
// Simple and intuitive: only 2 buttons ("Keep editing" or "Discard change").
function promptDraftConflict(reason) {
  return new Promise(resolve => {
    const dialog = $("#draft-switch-dialog");
    const titleEl = $("#draft-switch-title");
    const msgEl = $("#draft-switch-message");
    const reasonEl = $("#draft-switch-reason");
    const keepBtn = $("#draft-switch-keep");
    const discardBtn = $("#draft-switch-discard");
    const addBtn = $("#draft-switch-add");
    const title = partInfo(state.draft?.kind)?.title || "interior part";

    let done = false;
    const finish = proceed => {
      if (done) return;
      done = true;
      keepBtn.onclick = discardBtn.onclick = null;
      if (addBtn) addBtn.onclick = null;
      dialog.removeEventListener("cancel", onCancel);
      if (dialog.open) dialog.close();
      resolve(proceed);
    };
    const onCancel = event => { event.preventDefault(); finish(false); };

    reasonEl.textContent = reason || "";
    reasonEl.hidden = !reason;
    if (addBtn) addBtn.hidden = true;

    titleEl.textContent = "Discard This Change?";
    msgEl.textContent = `Your last change to this ${title} can't be saved yet, so leaving it now will lose that change.`;
    discardBtn.textContent = "Discard change";

    keepBtn.onclick = () => finish(false);
    discardBtn.onclick = () => {
      const index = draftCommitIndex();
      if (Number.isInteger(index) && state.design.layout.features[index]) {
        state.draft = clone(state.design.layout.features[index]);
        state.draftTouched = false;
      }
      finish(true);
    };

    dialog.addEventListener("cancel", onCancel);
    if (!dialog.open) dialog.showModal();
  });
}

// ---- Reusable application confirmation dialog (Fix 019 Item 8). One shared
// implementation instead of one-off native confirm()s or duplicated custom
// dialogs. Resolves "primary" / "secondary" / "cancel" — Escape (when the
// dialog is dismissible) and the dialog's own close behave as "cancel".
// Backdrop clicks are ignored: a required decision must end in a button
// press, never a stray click. Danger
// actions use the existing danger button styling and move focus to Cancel
// (the safe default); ordinary actions move focus to the primary button.
function appConfirm({
  title, message,
  primaryLabel = "OK", secondaryLabel = null, cancelLabel = "Cancel",
  danger = false, secondaryDanger = false, checkboxLabel = null,
  dismissible = true,
} = {}) {
  return new Promise(resolve => {
    const dialog = $("#app-confirm-dialog");
    const titleEl = $("#app-confirm-title");
    const msgEl = $("#app-confirm-message");
    const primaryBtn = $("#app-confirm-primary");
    const secondaryBtn = $("#app-confirm-secondary");
    const cancelBtn = $("#app-confirm-cancel");
    if (!dialog || !titleEl || !msgEl || !primaryBtn || !secondaryBtn || !cancelBtn) {
      // Markup missing (older cached HTML): fail safe to "cancel" rather
      // than silently proceeding with a destructive/ambiguous action.
      resolve("cancel");
      return;
    }

    const checkRow = $("#app-confirm-check-row");
    const checkBox = $("#app-confirm-check");
    if (checkRow && checkBox) {
      checkRow.hidden = !checkboxLabel;
      checkBox.checked = false;
      $("#app-confirm-check-label").textContent = checkboxLabel || "";
    }
    let done = false;
    const finish = choice => {
      if (done) return;
      done = true;
      // Read by callers that offered a checkbox (see appConfirm.checked).
      appConfirm.checked = Boolean(checkboxLabel && checkBox?.checked);
      primaryBtn.onclick = secondaryBtn.onclick = cancelBtn.onclick = null;
      dialog.removeEventListener("cancel", onCancel);
      dialog.removeEventListener("close", onClose);
      if (dialog.open) dialog.close();
      resolve(choice);
    };
    const onCancel = event => {
      event.preventDefault();
      if (dismissible) finish("cancel");
    };
    // A close event from the previous confirmation may arrive after this one opens.
    const onClose = () => { if (!dialog.open) finish("cancel"); };

    titleEl.textContent = title || "";
    msgEl.textContent = message || "";
    primaryBtn.textContent = primaryLabel;
    primaryBtn.classList.toggle("danger", danger);
    primaryBtn.classList.toggle("primary", !danger);
    cancelBtn.hidden = cancelLabel === null;
    cancelBtn.textContent = cancelLabel || "";
    if (secondaryLabel) {
      secondaryBtn.hidden = false;
      secondaryBtn.textContent = secondaryLabel;
      secondaryBtn.classList.toggle("danger", secondaryDanger);
    } else {
      secondaryBtn.hidden = true;
      secondaryBtn.classList.remove("danger");
    }

    primaryBtn.onclick = () => finish("primary");
    secondaryBtn.onclick = () => finish("secondary");
    cancelBtn.onclick = cancelLabel === null ? null : () => finish("cancel");

    dialog.addEventListener("cancel", onCancel);
    dialog.addEventListener("close", onClose);
    if (!dialog.open) dialog.showModal();
    // Focus always stays on a safe default - the primary action, or Cancel
    // when the primary itself is the dangerous one - never on a danger-
    // styled secondary button (e.g. "Discard & Switch").
    (danger && cancelLabel !== null ? cancelBtn : primaryBtn).focus();
  });
}

// Ordinary two-choice confirmation. Resolves true for the action, false for
// Cancel/Escape/backdrop.
async function appConfirmAction({ title, message, actionLabel = "OK", cancelLabel = "Cancel", danger = false, checkboxLabel = null }) {
  const choice = await appConfirm({ title, message, primaryLabel: actionLabel, cancelLabel, danger, checkboxLabel });
  // Read by callers that passed checkboxLabel (see appConfirm.checked).
  appConfirmAction.checked = appConfirm.checked;
  return choice === "primary";
}

// Used only for committing a 2D-layout drag of an already-placed support -
// a discrete one-shot action, unlike the continuous autoCommitDraft above.
async function applySupport(index) {
  if (!state.draft || !beginDesignMutation()) return;
  try {
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/apply", { design: state.design, feature: state.draft, index });
    state.design = result.design;
    noteCommittedDesignChange(previousDesign);
    state.selected = result.selected;
    state.draftIsNew = false;
    state.draftTouched = false;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[state.selected]);
    state.draftResolvedOptions = {};
    if (state.draft.kind === "nest") syncForm();
    renderDraftFields();
    renderPlaced();
    updateSelectionButtons();
    await refreshDraft();
    for (const warning of result.warnings || []) toast(warning, false, 6500);
    if (index === null && state.draft?.kind !== "text") await maybePromptSurfaceObjectHeight();
    return true;
  } catch (error) {
    toast(error.message, true, 5000);
    return false;
  } finally {
    finishDesignMutation();
  }
}