"use strict";

function renderDraftFields() {
  if (!state.draft) return;
  const info = partInfo();
  const one = state.draft;
  const zone = one.zone;
  const width = zone[2] - zone[0];
  const depth = zone[3] - zone[1];
  // Bore and Photo Nest carry their own identity inside their controls, so the
  // grey panel blurb just wastes space there.
  const descEl = $("#draft-description");
  if (descEl) {
    descEl.textContent = "";
    descEl.hidden = true;
  }
  let html = "";
  // Keys pulled up into the "Repeats" cluster, so the body loop skips them.
  const repeatKeys = new Set();
  // Fix 061 F1: Post and Steps describe the physical part before its repeat
  // layout, so their Repeats group is held back until the part fields exist.
  let repeatsHtml = "";
  let stepsSizeHtml = "";
  let cradleToolHtml = "";
  const editorGroup = (label, inner) =>
    `<div class="editor-group"><span class="editor-group-label">${label}</span>${inner}</div>`;
  if (one.kind === "scoop") {
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, "depth");
    const shown = explicit ? one.options.depth : state.draftResolvedOptions?.depth ?? 60;
    html += scoopDepthField("option:depth", shown);
  }
  if (one.kind === "nest") {
    html += renderNestFields(one);
  }
  if (info.flags.text) {
    const textLevel = one.options?.level === "rim" ? "rim" : "base";
    const textType = `${textLevel}_${one.options?.raised === true ? "raised" : "inlaid"}`;
    const textInput = `<input type="text" maxlength="80" data-draft="option:text" value="${escapeHtml(one.options?.text ?? "")}" placeholder="${textLevel === "rim" ? "e.g. M3 BOLTS" : "e.g. M3"}">`;
    let textGroup = `<label>Text${textInput}</label>`;
    // At most one rim Text is allowed per bin (Fix 078). Another Text's At-rim
    // choices are disabled once one rim Text already exists elsewhere. Shared
    // conditional-state explanation rule: the disabled choice names its
    // reason in its own label, matching the " (base too thin)" depth suffix.
    const hasOtherRimText = (state.design.layout?.features || []).some((feature, index) =>
      index !== state.selected && feature.kind === "text" && feature.options?.level === "rim");
    const styleLabel = `<label>Style<select data-draft="option:text_type">
      ${[["base_inlaid", "On base — inlaid"], ["base_raised", "On base — raised"], ["rim_inlaid", "At rim — inlaid"], ["rim_raised", "At rim — raised"]]
        .map(([value, label]) => {
          const rimBlocked = hasOtherRimText && value.startsWith("rim_");
          const rimSuffix = rimBlocked ? " (one At-rim text already used)" : "";
          return `<option value="${value}" ${value === textType ? "selected" : ""} ${rimBlocked ? "disabled" : ""}>${label}${rimSuffix}</option>`;
        }).join("")}
      </select></label>`;
    const capShown = textLevel === "rim"
      ? (state.draftResolvedOptions?.cap_height ?? one.options?.cap_height ?? 5)
      : (one.options?.cap_height ?? state.draftResolvedOptions?.cap_height ?? 15);
    const depthShown = number(one.options?.depth ?? state.draftResolvedOptions?.depth, 0.4);
    const depthLabel = one.options?.raised === true ? "Raised height" : "Inlay depth";
    const depthTip = one.options?.raised === true
      ? "How far the letters project above their receiving surface."
      : "Letters are recessed into the surface by this depth.";
    const letterField = field("Letter height", "option:cap_height", String(Math.floor(number(capShown, 15))), { unit: "mm", step: "1" });
    const depthChoices = textDepthChoices(info);
    const minimumBacking = number(textBackingRules().min_backing_mm, NaN);
    const receiving = textLevel === "base" ? baseTextReceivingThickness() : NaN;
    const disableBaseInlay = textLevel === "base" && one.options?.raised !== true;
    const knownDepth = depthChoices.some(choice => Math.abs(choice.value - depthShown) < 1e-6);
    const depthSelectLabel = `<label title="${depthTip}">${depthLabel}<select data-draft="option:depth">
      ${depthChoices.map(choice => {
        const tooThin = disableBaseInlay &&
          !inlayDepthLegal(choice.value, receiving, minimumBacking);
        const suffix = tooThin ? " (base too thin)" : "";
        return `<option value="${choice.value}" ${Math.abs(depthShown - choice.value) < 1e-6 ? "selected" : ""} ${tooThin ? "disabled" : ""}>${choice.label}${suffix}</option>`;
      }).join("")}
      ${knownDepth ? "" : `<option value="${depthShown}" selected>${depthShown} mm — Existing</option>`}
      </select></label>`;
    textGroup += `<div class="pair triple">${styleLabel}${letterField}${depthSelectLabel}</div>`;
    if (textLevel === "rim") {
      textGroup += `<label>Rim side<select data-draft="option:rim_side">${[["back", "Back"], ["front", "Front"], ["left", "Left"], ["right", "Right"]]
        .map(([value, label]) => `<option value="${value}" ${(one.options?.rim_side || "back") === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>`;
    } else {
      textGroup += `<label>Rotate<select id="draft-rotate">
        ${[0, 1, 2, 3].map(turn => `<option value="${turn}" ${(number(one.options?.quarter_turns, 0) % 4) === turn ? "selected" : ""}>${turn * 90}°</option>`).join("")}
      </select></label>`;
    }
    html += `<div class="editor-group">${textGroup}</div>`;
  }
  if (info.flags.size && one.kind !== "cradle" && !(one.kind === "text" && one.options?.level === "rim")) {
    const isPocket = one.kind === "pocket";
    const isBore = one.kind === "bore";
    const wall = isPocket ? number(one.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
    const reach = isPocket ? pocketWallReach(wall, one.options?.wall_style ?? state.draftResolvedOptions?.wall_style) : 0;
    const shownWidth = isPocket ? Math.max(0.1, width - 2 * reach) : width;
    const shownDepth = isPocket ? Math.max(0.1, depth - 2 * reach) : depth;
    // A bore's footprint reads Width x Length, matching Pocket and the item terms.
    // Slot and base Text each also carry their own "Depth" field (slot cut / letter
    // sink), so the footprint dimension is named apart to avoid two "Depth" boxes.
    const widthLabel = isPocket ? "Inside width" : one.kind === "slot" ? "Rack width" : "Width";
    const depthLabel = isPocket || isBore ? (isPocket ? "Inside length" : "Length")
      : one.kind === "slot" ? "Rack length"
      : one.kind === "text" ? "Text box depth"
      : "Depth";
    if (isBore) {
      const draftProfile = one.item?.profile || "round";
      const hexBit = isHexBitProfile(draftProfile);
      const boreItem = one.item || starterItem();
      const boreFirst = boreItem.segments[0] || { length: 40, diameter: 6 };
      // An option field always shows its current resolved number. An absent
      // stored option remains automatic and will update when its inputs do.
      const optionField = (key, label, opts = {}) => {
        const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
        const value = explicit ? one.options[key]
          : state.draftResolvedOptions?.[key] ?? info.fields.find(f => f.key === key)?.default;
        const displayValue = explicit ? value
          : key === "height" && heightMode === "manual" ? roundUpHalfMm(value)
            : boreDerivedDimension(key, value);
        const shown = opts.transform ? opts.transform(displayValue) : displayValue;
        const { transform, ...fieldOpts } = opts;
        return field(label, `option:${key}`, shown, fieldOpts);
      };
      const gridField = (key, label) => field(label, `option:${key}`,
        one.options?.[key] ?? state.draftResolvedOptions?.[key] ?? 1, { step: "1", min: "1" });
      // Fix 081 D: the size field is named for the hole shape it actually
      // cuts, not a generic "Diameter" that reads oddly for a square/diamond.
      const boreSizeLabels = { round: "Hole size", hex: "Hex size", square: "Diamond size", square_axis: "Square size" };
      const diameterLabel = boreSizeLabels[draftProfile] || "Diameter";
      // Diameter is locked to the preset for a hex-bit profile.
      const diameterField = hexBit
        ? `<label><span class="field-label">${diameterLabel}<span class="unit">mm</span></span>
            <input type="number" value="${HEX_BIT_PROFILES[draftProfile].diameter}" disabled></label>`
        : field(diameterLabel, "item_diameter", fmt(boreFirst.diameter), { unit: "mm" });
      const boreProfiles = [
        ["round", "Round"], ["hex", "Hex"], ["square", "Diamond"],
        ["square_axis", "Square"],
        ["hex_bit_short", HEX_BIT_PROFILES.hex_bit_short.label],
        ["hex_bit_long", HEX_BIT_PROFILES.hex_bit_long.label],
      ];
      // One persisted Style word (Fix 068): Base styles are a solid block the
      // holes are cut into; Walls Only builds just the perimeter sleeve(s)
      // rising from the floor.
      const boreStyle = boreStyleOf(one);
      const wallsOnly = boreWallsOnly(boreStyle);
      const xyMode = boreXyMode(one);
      const heightMode = boreHeightMode(one);
      const modeSelect = (label, key, value, choices) => `<label><span class="field-label">${label}</span><select data-draft="option:${key}">
        ${choices.map(([choice, text]) => `<option value="${choice}" ${value === choice ? "selected" : ""}>${text}</option>`).join("")}
      </select></label>`;
      const styleField = `<label><span class="field-label">Style</span><select data-draft="option:bore_style">
        ${BORE_STYLES.map(([value, label]) => `<option value="${value}" ${boreStyle === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>`;
      const boreWallShown = one.options?.wall ?? state.draftResolvedOptions?.wall ?? state.design?.box?.wall;
      const shapeField = `<label><span class="field-label">Shape</span><select data-draft="profile">
        ${boreProfiles.map(([value, label]) => `<option value="${value}" ${draftProfile === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>`;

      // Base: the zone the Bore occupies and the hole grid that fills it. Sizing
      // is one persistent mode per relationship (never a one-shot button); the
      // X / Y counts are always explicit.
      const xySelect = wallsOnly
        ? modeSelect("Set bin width / length", "xy_size_mode", xyMode, [
          ["manual", "Manually"], ["bin_to_bore", "Auto size bin to bore"]])
        : modeSelect("Set base width / length", "xy_size_mode", xyMode, [
          ["manual", "Manually"], ["bore_to_bin", "Auto size bore to bin"],
          ["bin_to_bore", "Auto size bin to bore"]]);
      const showXy = !wallsOnly && xyMode === "manual";
      const showHeight = heightMode !== "bore_to_bin";
      // Fix 081 C/D: Bore now names itself above its settings (like every
      // other option), so the old standalone "Type" card is gone - Style
      // instead sits on the left of the same row as Set base width / length.
      html += `<div class="bore-group wide bore-group-nolabel">
        <div class="bore-group-fields">
          <div class="bore-auto-row">
            ${styleField}
            ${xySelect}
          </div>
          ${showXy
            ? `<div class="bore-auto-row bore-auto-row-two">
                ${field("Width", "width", fmt(shownWidth), { unit: "mm", step: "1" })}
                ${field("Length", "depth", fmt(shownDepth), { unit: "mm", step: "1" })}
              </div>`
            : ""}
          <div class="bore-auto-row">
            ${modeSelect("Set height", "height_size_mode", heightMode, [
              ["manual", "Manually"], ["bore_to_bin", "Auto size bore to bin"],
              ["bin_to_bore", "Auto size bin to bore"]])}
            ${showHeight ? optionField("height", "Height", { unit: "mm", step: "0.5", min: "0.1" }) : ""}
          </div>
          <div class="bore-auto-row">
            ${gridField("columns", "X count")}${gridField("rows", "Y count")}
          </div>
        </div>
      </div>`;

      // Hole: everything about the holes cut into that block.
      const walllsOnlyDepthTip = "How far the held object can insert downward from the Bore mouth "
        + "before it hits its stop. Blank reaches the normal bin floor.";
      // Fix 081 D: Bore angle is now one of exactly eight fixed degrees
      // (never a free-typed number), defaulting to 90° - upright.
      const boreAngleSteps = [20, 30, 40, 50, 60, 70, 80, 90];
      const boreAngleField = () => {
        const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, "angle");
        const stored = explicit ? one.options.angle
          : state.draftResolvedOptions?.angle ?? info.fields.find(f => f.key === "angle")?.default ?? 0;
        const shown = 90 - number(stored, 0);
        const nearest = boreAngleSteps.reduce((best, value) =>
          Math.abs(value - shown) < Math.abs(best - shown) ? value : best, boreAngleSteps[0]);
        return `<label><span class="field-label">Bore angle<span class="unit">°</span></span>
          <select data-draft="option:angle" title="90° is upright. Smaller angles lean the Bore toward the selected direction.">
            ${boreAngleSteps.map(value => `<option value="${value}" ${value === nearest ? "selected" : ""}>${value}°</option>`).join("")}
          </select>
        </label>`;
      };
      html += `<div class="bore-group wide">
        <div class="bore-group-fields bore-hole-fields">
          ${diameterField}
          ${shapeField}
          ${wallsOnly
            ? optionField("walls_depth", "Depth", { unit: "mm", step: "0.5", min: "0.1", tip: walllsOnlyDepthTip })
            : optionField("depth", "Depth", { unit: "mm", step: "0.5", min: "0.1" })}
          ${wallsOnly ? dividerThicknessField(boreWallShown, "option:wall") : ""}
          ${hexBit || boreStyle !== "base_straight" ? "" : boreAngleField()}
          ${hexBit || boreStyle !== "base_straight" || number(one.options?.angle ?? state.draftResolvedOptions?.angle, 0) <= 1e-9 ? "" : `<label><span class="field-label">Angle towards</span><select data-draft="option:angle_towards">
            ${[["back", "Back"], ["front", "Front"], ["left", "Left"], ["right", "Right"]].map(([value, label]) => `<option value="${value}" ${(one.options?.angle_towards || (one.along === "y" ? "front" : "left")) === value ? "selected" : ""}>${label}</option>`).join("")}
          </select></label>`}
        </div>
      </div>`;
    } else if (isPocket || one.kind === "slot") {
      // Audit 006 J1: Pocket and Slot Rack group their related controls into
      // the same `.editor-group` language Bore/Divider already use, instead
      // of scattering Width/Length from Height/Wall/geometry across the
      // renderer's default field order. Every data-draft key, default source,
      // unit, min/step rule and autosize action below is identical to the
      // plain fields this replaces - only the markup/grouping changed.
      const isSlot = one.kind === "slot";
      const fieldFor = (key, label, opts = {}) => {
        const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
        const def = info.fields.find(f => f.key === key)?.default;
        const value = explicit ? one.options[key] : state.draftResolvedOptions?.[key] ?? def;
        return field(label, `option:${key}`, fmtBlank(value), opts);
      };
      const wallStyleShown = one.options?.wall_style ?? state.draftResolvedOptions?.wall_style
        ?? info.fields.find(f => f.key === "wall_style")?.default;
      const wallField = fieldFor("wall", "Wall", isSlot ? { unit: "mm", min: "0.1" } : { unit: "mm", min: "0.4" });
      const wallsField = wallStyleSelect(wallStyleShown);
      const sizeFieldsHtml = field(widthLabel, "width", fmt(shownWidth), { unit: "mm", step: "1" })
        + field(depthLabel, "depth", fmt(shownDepth), { unit: "mm", step: "1" })
        + (isSlot ? "" : fieldFor("depth", "Pocket depth", { unit: "mm", step: "0.5", min: "0.1" }))
        + fieldFor("height", "Height", isSlot ? { unit: "mm", min: "0.1" } : { unit: "mm", step: "0.5", min: "1.0" });
      html += `<div class="editor-group"><span class="editor-group-label">Size</span><div class="draft-triple">${sizeFieldsHtml}</div></div>`;
      if (isSlot) {
        const geometryFieldsHtml = fieldFor("thickness", "Slot width", { unit: "mm", min: "0.1" })
          + fieldFor("depth", "Slot depth", { unit: "mm", min: "0.1" })
          + fieldFor("angle", "Tilt angle", { unit: "°", min: "0", max: "45" });
        html += `<div class="editor-group"><span class="editor-group-label">Geometry</span><div class="draft-triple">${geometryFieldsHtml}</div></div>`;
      }
      html += `<div class="editor-group"><span class="editor-group-label">Walls</span><div class="pair">${wallField}${wallsField}</div></div>`;
    } else {
      const footprint = field(widthLabel, "width", fmt(shownWidth), { unit: "mm", step: "1" })
        + field(depthLabel, "depth", fmt(shownDepth), { unit: "mm", step: "1" });
      if (one.kind === "steps") stepsSizeHtml += footprint;
      else html += footprint;
    }
  }
  // Repeats: how many, how far apart, which way they run - one cluster, in
  // reading order, instead of Quantity / spacing / Runs along scattered apart.
  if (info.flags.qty || info.flags.along) {
    const htmlBeforeRepeats = html;
    html = "";
    // The part's own spacing / gap belongs with Quantity, not up in the body.
    let repeatFieldsHtml = "";
    for (const option of info.fields) {
      if (!["spacing", "floor_gap"].includes(option.key)) continue;
      if (info.kind === "cradle" && option.key === "floor_gap") continue;
      repeatKeys.add(option.key);
      // Grid dividers space their walls evenly on both axes; no spacing field.
      if (info.kind === "divider") continue;
      const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, option.key);
      const shown = explicit ? one.options[option.key]
        : state.draftResolvedOptions?.[option.key] ?? option.default;
      const fo = {};
      if (info.kind === "cradle" && option.key === "spacing") fo.min = 0;
      if (["cradle", "post"].includes(info.kind) && option.key === "spacing") fo.unit = "mm";
      repeatFieldsHtml += field(option.label, `option:${option.key}`, shown, fo);
    }

    if (info.kind === "divider") {
      // Two quantities instead of one direction: walls across X and walls
      // across Y, together making a grid of compartments.
      const opt = one.options || {};
      const legacyN = one.count == null ? 1 : Math.max(1, number(one.count, 1));
      const gx = (opt.count_x != null && opt.count_x !== "") ? opt.count_x
        : (one.along === "y" ? legacyN : 0);
      const gy = (opt.count_y != null && opt.count_y !== "") ? opt.count_y
        : (one.along === "x" ? legacyN : 0);
      const shownGx = (number(gx, 0) === 0) ? "" : gx;
      const shownGy = (number(gy, 0) === 0) ? "" : gy;
      const shownThickness = opt.thickness ?? state.draftResolvedOptions?.thickness ?? 1.6;
      const shownHeight = opt.height ?? state.draftResolvedOptions?.height ?? "";
      const wallStyle = opt.wall_style ?? state.draftResolvedOptions?.wall_style ?? "straight";
      html += `<div class="editor-group divider-layout"><span class="editor-group-label">Layout</span><div class="pair">
        ${field("X count", "option:count_x", shownGx, { min: "0", step: "1", tip: "Walls dividing the bin left to right. 0 for none." })}
        ${field("Y count", "option:count_y", shownGy, { min: "0", step: "1", tip: "Walls dividing the bin front to back. 0 for none." })}
      </div><div class="pair triple">
        ${dividerThicknessField(shownThickness)}
        ${field("Height", "option:height", fmtBlank(shownHeight), { unit: "mm", step: "0.5", min: "0.1" })}
        ${wallStyleSelect(wallStyle)}
      </div></div>`;
    } else {
      const autoPost = info.kind === "post" && one.count == null;
      const directionLabel = info.kind === "steps" ? "Shelf direction" : "Runs along";
      const runsAlong = info.flags.along && !["divider", "bore"].includes(info.kind) && !autoPost
        ? `<fieldset><legend>${directionLabel}</legend><div class="segmented two">
          <label><input type="radio" name="draft-along" value="x" ${one.along === "x" ? "checked" : ""}><span>X direction</span></label>
          <label><input type="radio" name="draft-along" value="y" ${one.along === "y" ? "checked" : ""}><span>Y direction</span></label>
        </div></fieldset>`
        : "";
      const hasOrientationControls = Boolean(info.flags.qty || repeatFieldsHtml || runsAlong || info.flags.alternate);
      if (hasOrientationControls) {
        html += `<div class="editor-group"><span class="editor-group-label">${info.flags.qty ? "Repeats" : "Orientation"}</span>`;
        // A part with no spacing field of its own (Slot Rack) would leave
        // Quantity alone on its row: Runs along takes the second column instead.
        const alongInPair = Boolean(info.flags.qty && !repeatFieldsHtml && runsAlong);
        if (info.flags.qty) {
          const quantityLabel = info.kind === "steps" ? "Number of steps" : "Quantity";
          const autoState = info.kind !== "steps" && one.count == null;
          html += `<div class="pair"><label><span class="field-label">${quantityLabel}${autoState ? " (Auto)" : ""}</span><div class="input-with-button">
            <input type="number" min="1" step="1" data-draft="count" value="${resolvedDraftCount(one)}">
            ${info.kind === "steps" ? "" : `<button type="button" class="button secondary" data-action="auto-count">Auto</button>`}
          </div></label>${repeatFieldsHtml}${alongInPair ? runsAlong : ""}</div>`;
          if (autoPost) html += `<p class="inline-help">Auto fills the available area with posts.</p>`;
          if (info.kind === "cradle") {
            const item = one.item || starterItem();
            const first = item.segments[0] || { length: 40, diameter: 6 };
            const tip = "Enter the tool's length and diameter. The cradle drops it into a half-circle notch and sizes its own ribs to the tool.";
            cradleToolHtml = editorGroup("Tool", `<div class="pair">${field("Length", "item_length", fmt(first.length), { unit: "mm", step: "1", tip })}${field("Diameter", "item_diameter", fmt(first.diameter), { unit: "mm", step: "1", tip })}</div>`);
          }
        } else if (repeatFieldsHtml) {
          html += `<div class="pair">${repeatFieldsHtml}</div>`;
        }
        if (info.flags.alternate) {
          html += `<label>End layout<select data-draft="alternate_ends">
            <option value="aligned" ${one.alternate_ends === true ? "" : "selected"}>Aligned</option>
            <option value="alternate" ${one.alternate_ends === true ? "selected" : ""}>Alternate ends</option>
          </select></label>`;
        }
        if (runsAlong && !alongInPair) html += runsAlong;
        if (info.flags.alternate) {
          // One field, two readings. Alternate ends on: the clearance kept at each
          // run end (writes end_margin). Off: a signed slide of the whole row along
          // the bin (writes run_offset). Each key keeps its own last value.
          const alternating = one.alternate_ends === true;
          const key = alternating ? "end_margin" : "run_offset";
          const label = alternating ? "From ends" : "Offset from center";
          const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
          const shown = explicit
            ? one.options[key]
            : alternating
            ? state.draftResolvedOptions?.end_margin ?? 10
            : 0;
          const tip = alternating
            ? "Share of the run kept clear at each end. Larger pulls the alternating troughs toward the middle; smaller pushes them to the ends."
            : "Slides the trough along the bin from centre, as a share of the room to the wall. Positive one way, negative the other; 0 stays centred.";
          // Fix 096 F12: browser bounds follow the backend option authority -
          // end_margin 0..45%, run_offset -100..100%.
          html += field(label, `option:${key}`, fmt(shown), { unit: "%", step: "1", tip,
            ...(alternating ? { min: "0", max: "45" } : { min: "-100", max: "100" }) });
        }
        html += `</div>`;
      }
    }
    repeatsHtml = html;
    html = htmlBeforeRepeats + cradleToolHtml;
  }
  if (!["post", "steps"].includes(info.kind)) html += repeatsHtml;
  if (info.flags.item && !["bore", "cradle"].includes(one.kind)) {
    // A bore's Diameter / Profile / Clearance are drawn in the "Hole" group above.
    const item = one.item || starterItem();
    const first = item.segments[0] || { length: 40, diameter: 6 };
    const isCradle = one.kind === "cradle";
    // Cradles use measured dimensions. Photo Nest has no item fields.
    const measuredStep = isCradle ? "1" : undefined;
    const lengthTip = isCradle
      ? "Enter the tool's length and diameter. The cradle drops it into a half-circle notch and sizes its own ribs to the tool."
      : undefined;
    // Fix 081 D: the size label matches the shape actually chosen below.
    const itemSizeLabels = { round: "Hole size", hex: "Hex size", square: "Square size" };
    const itemSizeLabel = isCradle ? "Diameter" : (itemSizeLabels[item.profile] || "Diameter");
    html += field("Length", "item_length", fmt(first.length), { unit: "mm", step: measuredStep, tip: lengthTip });
    html += field(itemSizeLabel, "item_diameter", fmt(first.diameter), { unit: "mm", step: measuredStep, tip: lengthTip });
    if (!isCradle) {
      const profiles = [["round", "Round"], ["hex", "Hex"], ["square", "Square"]];
      html += `<label>Shape<select data-draft="profile">
        ${profiles.map(([value, label]) => `<option value="${value}" ${item.profile === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>`;
      html += field("Fit clearance", "clearance", fmt(item.clearance ?? 0.4), {
        unit: "mm",
        tip: "Extra space around the object.",
      });
    }
  }
  let bodyHtml = "";
  for (const option of info.fields) {
    if (one.kind === "text" && one.options?.level === "rim") continue;
    // Rendered together as the one "% from end / Offset from center" field
    // beneath Runs along, above.
    if (option.key === "end_margin" || option.key === "run_offset") continue;
    // Pulled up into the "Repeats" cluster (spacing / floor gap).
    if (repeatKeys.has(option.key)) continue;
    // Every bore field is drawn up with the footprint above; nothing is left
    // for this loop.
    if (info.kind === "bore") continue;
    // Nest's fit numbers ride beside Lift assist; Text's letter size/depth ride
    // with the Text field.
    if (info.kind === "nest" && (option.key === "clearance" || option.key === "smoothing")) continue;
    if (info.kind === "text" && (option.key === "cap_height" || option.key === "depth")) continue;
    // Rendered by the Divider slope block below only for Crossbars.
    if (option.key === "bottom_supports") continue;
    // Slope and angle are handled specifically for divider below.
    if (info.kind === "divider" && ["bottom_angle", "angle", "thickness", "height", "wall_style"].includes(option.key)) continue;
    // The scoop depth field is rendered with its own % unit and help text above.
    if (info.kind === "scoop") continue;
    // Audit 006 J1: Pocket size/geometry/Walls are already rendered as
    // grouped fields above (Inside width/length, Pocket depth, Height, Wall,
    // Walls) - nothing is left for this loop.
    if (info.kind === "pocket" && ["height", "wall", "wall_style", "depth"].includes(option.key)) continue;
    // Audit 006 J1: Rack size/Slot geometry/Walls are already rendered above
    // (Rack width/length, Height, Slot width/depth, Tilt angle, Wall, Walls).
    if (info.kind === "slot" && ["height", "wall", "wall_style", "depth", "thickness", "angle"].includes(option.key)) continue;
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, option.key);
    const shown = explicit ? one.options[option.key]
      : state.draftResolvedOptions?.[option.key] ?? option.default;
    if (option.key === "wall_style") {
      bodyHtml += wallStyleSelect(shown);
      continue;
    }
    // Mouse-wheel / spinner steps: lean and slope a whole degree, width
    // half a mm.
    const stepFor = { angle: "1" };
    if (info.kind === "divider") {
      stepFor.thickness = "0.5";
      stepFor.bottom_angle = "1";
    }
    if (info.kind === "post") {
      stepFor.height = "1.0";
    }
    if (info.kind === "pocket") {
      stepFor.height = "0.5";
      stepFor.depth = "0.5";
      stepFor.wall = "0.1";
      stepFor.rounding = "0.1";
    }
    const fieldOpts = {};
    if (stepFor[option.key]) fieldOpts.step = stepFor[option.key];
    if (info.kind === "cradle" && option.key === "spacing") fieldOpts.min = 0;
    if (info.kind === "divider" && option.key === "spacing") fieldOpts.min = 0.1;
    if (info.kind === "post" && option.key === "height") fieldOpts.min = 0.1;
    if (info.kind === "post" && option.key === "diameter") fieldOpts.min = 0.1;
    if (info.kind === "post" && option.key === "taper") fieldOpts.min = 0;
    if (info.kind === "post" && option.key === "spacing") fieldOpts.min = 0;
    if (info.kind === "steps" && option.key === "height") fieldOpts.min = 0.1;
    if (info.kind === "steps" && option.key === "lip") fieldOpts.min = 0;
    if (info.kind === "pocket" && option.key === "rounding") fieldOpts.min = 0;
    if (info.kind === "pocket" && option.key === "wall") fieldOpts.min = 0.4;
    if (info.kind === "pocket" && option.key === "depth") fieldOpts.min = 0.1;
    if (info.kind === "pocket" && option.key === "height") fieldOpts.min = 1.0;
    const labels = {
      pocket: { depth: "Pocket depth" },
      slot: { depth: "Slot depth", thickness: "Slot width", angle: "Tilt angle" },
    };
    const mmKinds = new Set(["post", "pocket", "slot", "steps"]);
    if (mmKinds.has(info.kind) && option.key !== "angle") fieldOpts.unit = "mm";
    if (info.kind === "slot" && option.key === "angle") fieldOpts.unit = "°";
    bodyHtml += field(labels[info.kind]?.[option.key] || option.label, `option:${option.key}`, fmtBlank(shown), fieldOpts);
  }
  // Three-across for the kinds whose leftover body fields would otherwise leave
  // a half-empty row (matches the Width / Length / Height row at the top).
  if (info.kind === "post") {
    html += `<div class="draft-triple">${bodyHtml}</div>` + repeatsHtml;
  } else if (info.kind === "steps") {
    html += editorGroup("Size", `<div class="pair">${stepsSizeHtml}${bodyHtml}</div>`) + repeatsHtml;
  } else if (bodyHtml) {
    html += ["pocket", "slot"].includes(info.kind)
      ? `<div class="draft-triple">${bodyHtml}</div>`
      : bodyHtml;
  }
  if (info.kind === "divider") {
    const opt = one.options || {};
    const scoopConfig = opt.scoop && typeof opt.scoop === "object" && !Array.isArray(opt.scoop)
      ? opt.scoop : null;
    const hasSlope = !scoopConfig && (
      opt.slope_base === true || (opt.bottom_angle !== undefined && Number(opt.bottom_angle) !== 0)
    );

    const bottomMode = scoopConfig ? "scoop" : hasSlope ? "slope" : "flat";
    html += `<div class="editor-group divider-bottom-group">`;
    html += `<div class="divider-bottom-row"><label>Bottom type<select data-draft="option:bottom_mode">
      <option value="flat" ${bottomMode === "flat" ? "selected" : ""}>Flat</option>
      <option value="slope" ${bottomMode === "slope" ? "selected" : ""}>Sloped</option>
      <option value="scoop" ${bottomMode === "scoop" ? "selected" : ""}>Curved</option>
    </select></label>`;

    if (hasSlope) {
      const explicitAngle = Object.prototype.hasOwnProperty.call(opt, "bottom_angle");
      const angleVal = explicitAngle
        ? number(opt.bottom_angle, 45)
        : number(state.draftResolvedOptions?.bottom_angle, 20);
      const angleChoices = [10, 20, 30, 40, 45, 50, 60, 70, 80];
      const legacyAngle = angleChoices.includes(angleVal) ? "" : `<option value="${escapeHtml(angleVal)}" selected>${escapeHtml(angleVal)}° — Existing</option>`;
      html += `<label>Slope angle<select data-draft="option:bottom_angle">${angleChoices.map(angle =>
        `<option value="${angle}" ${angle === angleVal ? "selected" : ""}>${angle}°</option>`).join("")}${legacyAngle}</select></label>`;
    } else if (scoopConfig) {
      const scoopDepth = Object.prototype.hasOwnProperty.call(scoopConfig, "depth")
        ? number(scoopConfig.depth, 60) : number(state.draftResolvedOptions?.curved_default_depth, 60);
      const depthChoices = [10, 20, 30, 40, 50, 60, 70, 80, 90];
      const legacyDepth = depthChoices.includes(scoopDepth) ? "" : `<option value="${escapeHtml(scoopDepth)}" selected>${escapeHtml(scoopDepth)}% — Existing</option>`;
      html += `<label title="Every Divider compartment uses the same curved depth, starting at its front floor edge.">Curved depth<select data-divider-scoop-depth>${depthChoices.map(depth =>
        `<option value="${depth}" ${depth === scoopDepth ? "selected" : ""}>${depth}%</option>`).join("")}${legacyDepth}</select></label>`;
    } else {
      html += `<div class="divider-bottom-empty" aria-hidden="true"></div>`;
    }
    html += `</div>`;

    if (hasSlope) {
      const angleVal = Object.prototype.hasOwnProperty.call(opt, "bottom_angle")
        ? opt.bottom_angle : number(state.draftResolvedOptions?.bottom_angle, 20);
      const angleNum = number(angleVal, 0);
      const useBars = angleNum !== 0 && opt.minimal_bottom === true;
      const construction = useBars ? "crossbars" : "solid";
      html += `<div class="pair divider-slope-options"><div class="divider-slope-fields">`;
      html += `<label>Slope construction<select data-draft="option:slope_construction">
        <option value="solid" ${construction === "solid" ? "selected" : ""}>Solid</option>
        <option value="crossbars" ${construction === "crossbars" ? "selected" : ""}>Crossbars</option>
      </select></label>`;
      if (angleNum !== 0) {
        if (useBars) {
          const explicitBars = Object.prototype.hasOwnProperty.call(opt, "bottom_supports");
          const bars = explicitBars
            ? opt.bottom_supports
            : state.draftResolvedOptions?.bottom_supports ?? 3;
          html += field("Crossbars", "option:bottom_supports", bars, { step: "1" });
        }
      }
      html += `</div><div class="divider-slope-toggles">`;
      html += toggle("option:alternate_bottom", "Alternate slopes",
        "Reverses every second tool slot.", opt.alternate_bottom === true);
      html += `</div></div>`;
    }

    html += `</div>`;

    if (!b4bEnabled()) {
      const hasLabels = opt.label_divisions === true;
      const labelType = !hasLabels ? "none" : opt.division_level === "rim" ? "rim" : "base";
      html += `<div class="editor-group"><span class="editor-group-label">Labels</span>`;
      html += `<label>Label type<select data-draft="option:label_type">
        <option value="none" ${labelType === "none" ? "selected" : ""}>No label</option>
        <option value="base" ${labelType === "base" ? "selected" : ""}>On base</option>
        <option value="rim" ${labelType === "rim" ? "selected" : ""}>Rim level</option>
      </select></label>`;

      if (hasLabels) {
        // A cell per compartment: (Qty X + 1) columns by (Qty Y + 1) rows,
        // laid out to mirror the bin so a label lands where its slot is.
        const legacyN = one.count == null ? 1 : Math.max(1, number(one.count, 1));
        let gcX = number(opt.count_x, NaN);
        if (!Number.isFinite(gcX)) gcX = one.along === "y" ? legacyN : 0;
        let gcY = number(opt.count_y, NaN);
        if (!Number.isFinite(gcY)) gcY = one.along === "x" ? legacyN : 0;
        gcX = Math.max(0, Math.round(gcX));
        gcY = Math.max(0, Math.round(gcY));
        const nCols = gcX + 1;
        const nRows = gcY + 1;
        let divLabels = [];
        if (Array.isArray(opt.division_labels)) {
          divLabels = opt.division_labels;
        } else if (typeof opt.division_labels === "string") {
          try {
            divLabels = JSON.parse(opt.division_labels);
          } catch {
            divLabels = opt.division_labels.split(",");
          }
        }

        const topology = dividerCompartmentsClient(one);
        html += `<div class="division-table division-grid" data-grid-columns="${nCols}" data-grid-rows="${nRows}">`;
        for (const cell of topology.cells) {
          const idx = cell.row * nCols + cell.column;
          const val = escapeHtml(String(divLabels[idx] || ""));
          html += `<input type="text" data-division-index="${idx}" data-grid-column="${cell.column + 1}" data-grid-column-span="${cell.columnSpan}" data-grid-row="${cell.row + 1}" data-grid-row-span="${cell.rowSpan}" value="${val}" placeholder="Optional label">`;
        }
        html += `</div>`;
      }
      html += `</div>`;
    }
  }
  // The auto-size buttons sit at the very bottom of the editor.
  if (!(one.kind === "text" && one.options?.level === "rim")) {
    html += renderFitActions(one);
  }
  // Informational only - a legal fused part above the rim still generates
  // fine. No checkbox, no warning styling; just a plain note of the fact.
  html += `<p class="inline-help" data-draft-overhang hidden></p>`;
  if (["pocket", "post", "slot", "steps"].includes(one.kind)) {
    const ready = one.kind !== "nest" || (one.contour && _nestMeasuredThickness(one.options) != null);
    let referenceFields = `<p class="inline-help">Reference only — does not resize this holder. Shown in 3D Preview.</p>`;
    if (one.reference_object) {
      let axisFields = "";
      for (const [axis, title] of [["width", "Width (X)"], ["depth", "Depth (Y)"], ["height", "Height (Z)"]]) {
        axisFields += field(title, axis, String(one.reference_object[axis]),
          { unit: "mm", min: "0", step: "any", dataAttribute: "data-reference-axis" });
      }
      referenceFields += `<div class="pair triple">${axisFields}</div>`;
      referenceFields += `<button type="button" class="button secondary" data-action="remove-reference">Remove reference</button>`;
    } else if (ready) {
      referenceFields += `<button type="button" class="button secondary" data-action="add-reference" ${referenceAddReady() ? "" : "hidden"}>Add object reference</button>`;
    }
    html += editorGroup("Reference object", referenceFields);
  }
  const activeDraft = document.activeElement?.dataset?.draft;
  $("#draft-fields").innerHTML = html;
  applyDivisionGridLayout($("#draft-fields"));
  if (one.kind === "divider" && dividerLockedByLidLabels()) {
    $$('input, select, button', $("#draft-fields")).forEach(control => { control.disabled = true; });
    $("#draft-status").textContent = dividerLockMessage();
  }
  updateDraftOverhangNote();
  syncNest2DWorkspace();
  const photoInput = $("#nest-photo-input", $("#draft-fields"));
  if (photoInput) photoInput.addEventListener("change", uploadNestPhoto);
  $$('[data-draft]', $("#draft-fields")).forEach(input => {
    // A Bore angle/direction is a committed transaction. Raw typing stays in
    // the control until change; growth is proved before the draft is touched.
    if (state.draft?.kind === "bore" &&
        ["option:angle", "option:angle_towards"].includes(input.dataset.draft)) return;
    input.addEventListener(input.tagName === "SELECT" ? "change" : "input", updateDraftFromFields);
  });
  if (activeDraft) {
    const el = $(`[data-draft="${activeDraft}"]`, $("#draft-fields"));
    if (el) el.focus();
  }
  const dividerAngle = $('[data-draft="option:bottom_angle"]', $("#draft-fields"));
  if (typeof dividerAngle?.select === "function") dividerAngle.addEventListener("focus", () => dividerAngle.select());
  $$('input[data-division-index]', $("#draft-fields")).forEach(input => input.addEventListener("input", () => {
    markDraftChanged();
    state.draft.options ||= {};
    let labels = Array.isArray(state.draft.options.division_labels) ? [...state.draft.options.division_labels] : [];
    const idx = parseInt(input.dataset.divisionIndex, 10);
    labels[idx] = input.value;
    state.draft.options.division_labels = labels;
    seedPartNameFromLabel(input.value);
    renderLayout2D();
    refreshDraftSoon();
  }));
  const scoopDepth = $('[data-divider-scoop-depth]', $("#draft-fields"));
  if (scoopDepth) scoopDepth.addEventListener("change", () => {
    markDraftChanged();
    state.draft.options ||= {};
    const config = state.draft.options.scoop ||= {};
    const raw = scoopDepth.value.trim();
    if (raw === "") delete config.depth;
    else config.depth = number(raw, state.draftResolvedOptions?.curved_default_depth ?? 60);
    state.draftAutoCommit = true;
    renderLayout2D();
    refreshDraftSoon();
  });
  const textInput = $('[data-draft="option:text"]', $("#draft-fields"));
  if (textInput) {
    const clearIfLabel = () => {
      if (textInput.value.trim().toLowerCase() === "label") {
        textInput.value = "";
        textInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    };
    textInput.addEventListener("focus", clearIfLabel);
    textInput.addEventListener("click", clearIfLabel);
  }
  // Width/Depth are floored to a minimum footprint below - reflect that back
  // once the user leaves the field, so a typed 0 or -5 doesn't keep showing
  // as though it were still in effect while a different error is displayed.
  $$('[data-draft="width"], [data-draft="depth"]', $("#draft-fields")).forEach(input => {
    input.addEventListener("blur", () => {
      const zone = state.draft.zone;
      const isPocket = state.draft.kind === "pocket";
      const wall = isPocket ? number(state.draft.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
      let actual = input.dataset.draft === "width" ? zone[2] - zone[0] : zone[3] - zone[1];
      if (isPocket) actual = Math.max(0.1, actual - 2 * wall);
      if (fmt(actual) !== input.value) input.value = fmt(actual);
    });
  });
  // Quantity is floored to 1 below (blank/"auto" stays open-ended) - same
  // reasoning as Width/Depth above: reflect the floor back so a typed 0
  // doesn't keep showing while one is actually placed.
  const countField = $('[data-draft="count"]', $("#draft-fields"));
  const syncCountAutoHint = () => {};
  if (countField) {
    countField.addEventListener("blur", () => {
      if (state.draft.count != null && String(state.draft.count) !== countField.value) {
        countField.value = String(state.draft.count);
      }
    });
  }
  $$('input[name="draft-along"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    markDraftChanged();
    state.draft.along = input.value;
    if (state.draft.kind === "cradle") sizeCradleToItem(state.draft);
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  $$('input[name="draft-wedge"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    markDraftChanged();
    state.draft.wedge = input.value === "wedge";
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  const rotateSelect = $("#draft-rotate", $("#draft-fields"));
  if (rotateSelect) rotateSelect.addEventListener("change", () => {
    markDraftChanged();
    state.draft.options ||= {};
    state.draft.options.quarter_turns = Number(rotateSelect.value) % 4;
    // The zone was fitted to the old orientation; swap its sides so the
    // lettering keeps roughly the same size after the quarter turn.
    const zone = state.draft.zone;
    const cx = (zone[0] + zone[2]) / 2, cy = (zone[1] + zone[3]) / 2;
    const w = zone[2] - zone[0], d = zone[3] - zone[1];
    state.draft.zone = [cx - d / 2, cy - w / 2, cx + d / 2, cy + w / 2];
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  });
  const autoCount = $('[data-action="auto-count"]', $("#draft-fields"));
  if (autoCount) autoCount.addEventListener("click", () => {
    markDraftChanged();
    state.draft.count = null;
    if (state.draft.kind === "cradle") sizeCradleToItem(state.draft);
    state.draftAutoCommit = true;
    renderDraftFields();
    updateSelectionButtons();
    refreshDraftSoon();
  });
  // The three per-part auto-size buttons (see renderFitActions).
  const fitBtn = $('[data-action="fit-part"]', $("#draft-fields"));
  if (fitBtn) fitBtn.addEventListener("click", fitPartToContents);
  const fillBtn = $('[data-action="fill-part"]', $("#draft-fields"));
  if (fillBtn) fillBtn.addEventListener("click", fillPartToBin);
  const growBtn = $('[data-action="grow-bin"]', $("#draft-fields"));
  if (growBtn) growBtn.addEventListener("click", event => autoExpandBin({ button: event.currentTarget }));
  updateFitActions();
  if (state.draft?.kind === "nest") wireNestFieldActions();
  $('[data-action="add-reference"]', $("#draft-fields"))?.addEventListener("click", addReferenceToCurrentDraft);
  $('[data-action="remove-reference"]', $("#draft-fields"))?.addEventListener("click", removeReferenceFromCurrentDraft);
  $$('[data-reference-axis]', $("#draft-fields")).forEach(input => input.addEventListener("input", () => {
    const valid = input.value.trim() !== "" && Number.isFinite(Number(input.value)) && Number(input.value) > 0;
    input.setCustomValidity(valid ? "" : "Enter a positive number of mm.");
    if (!valid) return;
    markDraftChanged(true);
    updateReferenceAxis(state.draft, input.dataset.referenceAxis, input.value);
    state.draftAutoCommit = true;
    state.referenceEditPending = true;
    commitReferenceEditSoon();
  }));
  if (state.draft?.kind === "bore") {
    const fields = $("#draft-fields");
    const angleField = $('[data-draft="option:angle"]', fields);
    const directionField = $('[data-draft="option:angle_towards"]', fields);
    if (angleField) angleField.addEventListener("change", commitBoreAngleChange);
    if (directionField) directionField.addEventListener("change", commitBoreAngleChange);
  }
  syncDraftFieldProblems();
}

// Fix 1008: local, visible validation for silently-invalid numeric fields.
// Python stays authoritative; these messages sit beside the field, following
// the edgeMountInputProblems() pattern. The out-of-range value is still what
// the design (and so print) sees. Blank is automatic and valid for every
// field here, so blank never produces a message.
function draftFieldProblems() {
  const problems = {};
  const kind = state.draft?.kind;
  const fields = [];
  if (kind === "bore") {
    fields.push({ key: "height", name: "Bore height", dataDraft: "option:height" });
    // Walls Only styles render the depth as option:walls_depth instead of
    // option:depth; only one of the two exists at a time.
    const depthKey = $('#draft-fields input[data-draft="option:depth"]')
      ? "option:depth" : "option:walls_depth";
    fields.push({ key: "depth", name: "Bore depth", dataDraft: depthKey });
  } else if (kind === "post") {
    fields.push({ key: "height", name: "Post height", dataDraft: "option:height" });
  } else if (kind === "divider") {
    fields.push({ key: "height", name: "Divider height", dataDraft: "option:height" });
  }
  for (const { key, name, dataDraft } of fields) {
    const input = $(`#draft-fields input[data-draft="${dataDraft}"]`);
    if (!input) continue;
    const raw = (input.value ?? "").trim();
    if (raw === "") continue; // blank = automatic, valid
    const value = Number(raw);
    const min = Number(input.min || "0.1"); // verified: 0.1 for all four fields
    const errorId = `draft-${key}-error`;
    if (!Number.isFinite(value)) {
      problems[key] = { message: `${name} must be a number — enter 0.1 mm or more.`, errorId, input };
    } else if (value < min) {
      problems[key] = { message: `${name} must be at least ${min} mm.`, errorId, input };
    } else if (key === "depth") {
      // Backend rule: depth no more than the height (+ 1e-9 tolerance).
      const hRaw = ($('#draft-fields input[data-draft="option:height"]')?.value ?? "").trim();
      let H = Number(hRaw) >= 0.1 ? Number(hRaw) : NaN;
      if (!Number.isFinite(H)) {
        const resolved = state.draftResolvedOptions?.height;
        H = Number.isFinite(Number(resolved)) && Number(resolved) > 0 ? Number(resolved) : NaN;
      }
      if (Number.isFinite(H) && value > H + 1e-9) {
        problems[key] = {
          message: `Bore depth cannot be more than the bore height of ${fmt(H)} mm.`,
          errorId, input,
        };
      }
    }
  }
  // Dividers Y count: empty is valid (0 = none) — guidance only, never an error.
  if (kind === "divider") {
    const input = $('#draft-fields input[data-draft="option:count_y"]');
    if (input && (input.value ?? "").trim() === "") {
      problems.count_y = {
        message: "Walls dividing the bin front to back. 0 for none.",
        errorId: "draft-count_y-guidance", input, guidance: true,
      };
    }
  }
  return problems;
}

function syncDraftFieldProblems() {
  const problems = draftFieldProblems();
  const seen = new Set();
  for (const [key, { message, errorId, input, guidance }] of Object.entries(problems)) {
    seen.add(errorId);
    let node = document.getElementById(errorId);
    if (!node) {
      node = document.createElement("p");
      node.id = errorId;
      node.className = guidance ? "inline-help" : "field-error";
      if (!guidance) node.setAttribute("role", "alert");
      node.hidden = true;
      input.closest("label")?.appendChild(node);
    }
    node.textContent = message;
    node.hidden = false;
    if (!guidance) input.toggleAttribute("aria-invalid", true);
  }
  // Clear any error/guidance nodes from a previous check that no longer apply.
  for (const id of ["draft-height-error", "draft-depth-error", "draft-count_y-guidance"]) {
    if (seen.has(id)) continue;
    const node = document.getElementById(id);
    if (node) node.hidden = true;
    const input = node?.closest("label")?.querySelector("input");
    input?.toggleAttribute("aria-invalid", false);
  }
  return problems;
}
