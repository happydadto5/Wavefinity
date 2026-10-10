"use strict";

// Fix 034 H inset_v2 semantics: 0 means the opening reaches that edge
// (floor for bottom, rim for top); a higher percentage pulls it inward.
const SIDE_OPENING_DEFAULTS = {
  enabled: false, shape: "curved", sides: [], size: "medium",
  from_bottom_percent: 10, from_top_percent: 15,
};
const SIDE_OPENING_SIDE_IDS = ["front", "back", "left", "right"];
let sideOpeningAdjustmentNote = "";

function sideOpeningState(design = state.design) {
  return { ...SIDE_OPENING_DEFAULTS, ...(design?.box?.side_openings || {}) };
}

function sideOpeningPartActive(design = state.design) {
  return Boolean(design?.box?.side_openings?.enabled);
}

const MODIFIER_SIDE_TO_WALL = {
  front: "-y",
  back: "+y",
  left: "-x",
  right: "+x",
};

const MODIFIER_OPPOSITE_SIDE = {
  front: "back",
  back: "front",
  left: "right",
  right: "left",
};

const MODIFIER_SIDE_LABEL = {
  front: "Front",
  back: "Back",
  left: "Left",
  right: "Right",
};

function insideGripWalls(box) {
  const grip = box?.lift_grabbers;
  if (!grip?.enabled) return new Set();
  if (grip.location === "sides") return new Set(["-x", "+x"]);
  if (grip.location === "front_back") return new Set(["-y", "+y"]);
  if (grip.location === "both") return new Set(["-x", "+x", "-y", "+y"]);
  return new Set();
}

function rimLabelSidesForDesign(design) {
  const sides = new Set();
  for (const feature of design?.layout?.features || []) {
    if (feature.kind !== "text" || feature.options?.level !== "rim") continue;
    const side = feature.options?.rim_side || "back";
    if (SIDE_OPENING_SIDE_IDS.includes(side)) sides.add(side);
  }
  if (String(design?.label || "").trim() && !sides.size) {
    const side = design.label_position === "top" ? "back" : design.label_position;
    if (SIDE_OPENING_SIDE_IDS.includes(side)) sides.add(side);
  }
  return sides;
}

function modifierConflicts(design) {
  const conflicts = [];
  const box = design?.box || {};
  const sideOpenings = sideOpeningState(design);
  const openSides = sideOpenings.enabled
    ? new Set(sideOpenings.sides || [])
    : new Set();
  const gripWalls = insideGripWalls(box);

  for (const side of SIDE_OPENING_SIDE_IDS) {
    if (!openSides.has(side)) continue;
    if (gripWalls.has(MODIFIER_SIDE_TO_WALL[side])) {
      conflicts.push({
        key: `side-opening:inside-grip:${side}`,
        message:
          `The ${MODIFIER_SIDE_LABEL[side]} wall already has a Side Opening. ` +
          "Move the Inside Grip to a different wall or remove that Side Opening.",
      });
    }
  }

  const edgeMount = box.edge_mount || {};
  if ((edgeMount.label_enabled || edgeMount.holes_enabled) &&
      openSides.has(edgeMount.side)) {
    conflicts.push({
      key: `side-opening:edge-mount:${edgeMount.side}`,
      message:
        `The ${MODIFIER_SIDE_LABEL[edgeMount.side]} wall already has a Side Opening. ` +
        "Choose another Edge Mount wall or remove that Side Opening.",
    });
  }

  const rimSides = rimLabelSidesForDesign(design);
  for (const rimSide of rimSides) {
    if (openSides.has(rimSide)) conflicts.push({
      key: `side-opening:rim-label:${rimSide}`,
      message: `The ${MODIFIER_SIDE_LABEL[rimSide]} wall already has a Side Opening. ` +
        "Put the rim Text on another wall or remove that Side Opening.",
    });
  }

  if (edgeMount.label_enabled && edgeMount.label_type === "separate") {
    const edgeSide = SIDE_OPENING_SIDE_IDS.includes(edgeMount.side)
      ? edgeMount.side
      : "front";
    if (rimSides.has(edgeSide)) {
      conflicts.push({
        key: `edge-mount-separate:rim-label:${edgeSide}`,
        message:
          `A Separate Edge Mount label and rim label cannot use the same ${MODIFIER_SIDE_LABEL[edgeSide]} wall. ` +
          "Move the rim label, choose another Edge Mount wall, or use Integrated.",
      });
    }
    if (box.lid?.enabled || box.stack?.mode === "lid") {
      conflicts.push({
        key: "edge-mount-separate:lid",
        message:
          "A Separate Edge Mount label cannot be used with a lid. " +
          "Use Integrated or remove the lid.",
      });
    }
    if (box.stack?.mode === "direct") {
      conflicts.push({
        key: "edge-mount-separate:direct-stack",
        message:
          "A Separate Edge Mount label cannot be used with direct Stackable Bin because " +
          "its inside clip occupies the stacking opening. Use Integrated or turn off direct stacking.",
      });
    }
  }

  if (edgeMount.holes_enabled) {
    const side = SIDE_OPENING_SIDE_IDS.includes(edgeMount.side)
      ? edgeMount.side
      : "front";
    const opposite = MODIFIER_OPPOSITE_SIDE[side];
    const mountWall = MODIFIER_SIDE_TO_WALL[side];
    const accessWall = MODIFIER_SIDE_TO_WALL[opposite];
    if (gripWalls.has(mountWall) || gripWalls.has(accessWall)) {
      conflicts.push({
        key: `edge-mount-holes:inside-grip:${side}`,
        message:
          `Edge Mount screw access needs both the ${MODIFIER_SIDE_LABEL[side]} wall ` +
          `and opposite ${MODIFIER_SIDE_LABEL[opposite]} wall clear of Inside Grips. ` +
          "Move the Inside Grip, choose another Edge Mount wall, or turn off Screw Mounting.",
      });
    }
  }

  if (design?.scoop && gripWalls.has("-y")) {
    const usableHeight = number(box.z) - number(box.base_thickness);
    const scoopTop = number(box.base_thickness)
      + usableHeight * number(state.catalog?.scoop_rules?.height_fraction, 0.6);
    const selectedSize = box.lift_grabbers?.size || "medium";
    const sizeRule = (state.catalog?.lift_grabbers?.sizes || [])
      .find(one => one.value === selectedSize);
    const grabberHeight = Number(sizeRule?.height_mm);
    const rimClearance = Number(state.catalog?.lift_grabbers?.rim_clearance_mm);
    if (Number.isFinite(grabberHeight) && Number.isFinite(rimClearance)) {
      const grabberBottom = number(box.z) - rimClearance - grabberHeight;
      if (scoopTop > grabberBottom) {
        conflicts.push({
          key: "scoop:inside-grip:front",
          message:
            "The front scoop rises into the front Inside Grip. Use side-only Inside Grip, " +
            "choose a smaller grip that clears, make the bin taller, or turn off the scoop.",
        });
      }
    }
  }

  return conflicts;
}

function newModifierConflict(previousDesign, nextDesign) {
  const previousKeys = new Set(
    modifierConflicts(previousDesign).map(conflict => conflict.key)
  );
  return modifierConflicts(nextDesign)
    .find(conflict => !previousKeys.has(conflict.key)) || null;
}

function rejectModifierConflict(previousDesign, previousCanGenerate, conflict) {
  state.design = previousDesign;
  // The restored design is the one the last preview measured, so its lid
  // thickness values are authoritative again.
  if (state.lidThicknessReport && state.lidThicknessReport.key === lidThicknessKey(state.design)) {
    state.lidThicknessEpoch = state.lidThicknessReport.epoch;
  }
  state.canGenerate = previousCanGenerate;
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  sideOpeningAdjustmentNote = "";
  syncForm();
  settleLidThicknessFormKey();
  updateGenerateAvailability();
  toast(conflict.message, true, 6000);
}

function applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate) {
  updateDesignFromForm();
  const conflict = newModifierConflict(previousDesign, state.design);
  if (!conflict) return true;
  rejectModifierConflict(previousDesign, previousCanGenerate, conflict);
  return false;
}

function applyPendingLiveFormWithModifierConflictGuard() {
  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;
  return applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate);
}

// Wall span a Side Opening's width is measured against - Front/Back run
// along X, Left/Right run along Y. Mirrors organizer_side_openings.
// side_opening_side_span() so the UI can filter eligibility client-side.
function sideOpeningSideSpan(side, design = state.design) {
  const box = design?.box || {};
  return side === "front" || side === "back" ? number(box.x) : number(box.y);
}

// Shared conditional-state explanation rule: a choice disabled by
// eligibility names its exact reason in its own label, never as a bare
// disabled control. The material reason comes first - a wall too short for
// the minimum opening width - then the conflicts that can also block a wall
// (Inside Grip, Edge Mount, rim Text).
function sideOpeningWallBlockedReason(side, design = state.design) {
  const rules = state.catalog?.side_openings || {};
  const minSide = number(rules.min_side_mm, 16);
  const box = design?.box || {};
  if (sideOpeningSideSpan(side, design) < minSide - 1e-9)
    return `wall too short (needs ${fmt(minSide)} mm)`;
  if (insideGripWalls(box).has(MODIFIER_SIDE_TO_WALL[side]))
    return "Inside Grip is on this wall";
  if ((box.edge_mount?.label_enabled || box.edge_mount?.holes_enabled) &&
      box.edge_mount.side === side) return "Edge Mount is on this wall";
  if (rimLabelSidesForDesign(design).has(side)) return "rim Text is on this wall";
  return "";
}

function sideOpeningEligibleSide(side, design = state.design) {
  return sideOpeningWallBlockedReason(side, design) === "";
}

// BEGIN SIDE_OPENING_SELECTION_HELPER
function reconcileSideOpeningSelection(selectedSides, eligibleSides) {
  const eligible = new Set(eligibleSides);
  const sides = selectedSides.filter(side => eligible.has(side));
  const removed = selectedSides.filter(side => !eligible.has(side));
  let replacement = null;
  if (!sides.length && eligibleSides.length) {
    replacement = eligibleSides[0];
    sides.push(replacement);
  }
  return { sides, removed, replacement };
}
// END SIDE_OPENING_SELECTION_HELPER

function reconcileSideOpeningsAfterResize(design) {
  sideOpeningAdjustmentNote = "";
  const current = sideOpeningState(design);
  if (!current.enabled) return;

  const eligibleSides = SIDE_OPENING_SIDE_IDS.filter(side => sideOpeningEligibleSide(side, design));
  const result = reconcileSideOpeningSelection(current.sides || [], eligibleSides);
  if (!result.sides.length) {
    design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    return;
  }

  design.box.side_openings = { ...current, enabled: true, sides: result.sides };
  const allowed = sideOpeningAllowedSizes(design);
  if (allowed.length && !allowed.includes(design.box.side_openings.size)) {
    design.box.side_openings.size = allowed[allowed.length - 1];
  }

  if (result.removed.length) {
    const removed = result.removed.map(side => side[0].toUpperCase() + side.slice(1)).join(" and ");
    const replacement = result.replacement
      ? ` ${result.replacement[0].toUpperCase() + result.replacement.slice(1)} was selected instead.`
      : "";
    const verb = result.removed.length === 1 ? "was" : "were";
    const wall = result.removed.length === 1 ? "that wall is" : "those walls are";
    sideOpeningAdjustmentNote = `${removed} ${verb} turned off because ${wall} now shorter than 2 units (16 mm).${replacement}`;
  }
}

// Python remains authoritative for real validation/geometry; this mirrors
// organizer_side_openings._vertical_fits() only for the immediate size-list
// filtering while typing.
function sideOpeningVerticalFits(design, spec, widthMm) {
  const box = design?.box || {};
  const floorZ = number(box.base_thickness);
  const rimZ = number(box.z);
  const usable = rimZ - floorZ;
  const bottomZ = floorZ + usable * (number(spec.from_bottom_percent, 0) / 100);
  const topZ = rimZ - usable * (number(spec.from_top_percent, 0) / 100);
  const r = widthMm / 2;
  if (bottomZ < floorZ - 1e-9) return false;
  if (topZ <= bottomZ + 1e-9) return false;
  if (number(spec.from_top_percent, 0) <= 1e-9) {
    return spec.shape === "curved" ? (rimZ - bottomZ) >= r - 1e-9 : true;
  }
  return spec.shape === "curved"
    ? (topZ - bottomZ) >= 2.5 * r - 1e-9
    : (topZ - bottomZ) >= r - 1e-9;
}

// Sizes that fit every currently-selected side at the current shape/depth/
// top-support combination. Mirrors organizer_side_openings.
// side_opening_allowed_sizes() so the browser never offers an impossible
// preset, but Python still re-validates on every preview/generate.
function sideOpeningAllowedSizes(design = state.design) {
  const rules = state.catalog?.side_openings || {};
  const sizes = rules.sizes || [];
  const margin = number(rules.corner_margin_mm, 4);
  const so = sideOpeningState(design);
  const spans = (so.sides || []).map(side => sideOpeningSideSpan(side, design));
  return sizes.filter(entry => {
    if (spans.some(span => entry.width_mm > span - 2 * margin + 1e-9)) return false;
    return sideOpeningVerticalFits(design, so, entry.width_mm);
  }).map(entry => entry.value);
}

function sideOpeningLidStackForced(design = state.design) {
  return lidPartActive(design);
}

// Fix 034 H: renamed from the old MaxFromTop - with inset_v2 semantics the
// Lid/Stack bridge is now a MINIMUM top inset (a higher % from top means
// more material left at the rim), not a maximum.
function sideOpeningMinFromTop(design = state.design) {
  const box = design?.box || {};
  const usable = number(box.z) - number(box.base_thickness);
  const bridge = number(state.catalog?.side_openings?.top_bridge_mm, 4);
  return usable > 0 ? 100 * bridge / usable : 0;
}

function clampSideOpeningTopForLid(design = state.design, flash = false) {
  const current = sideOpeningState(design);
  if (!current.enabled || !sideOpeningLidStackForced(design)) return;
  const minimum = Math.max(0, sideOpeningMinFromTop(design));
  if (number(current.from_top_percent, 0) < minimum) {
    design.box.side_openings = { ...current, from_top_percent: minimum };
    if (flash) flashField($("#side-opening-upper"));
  }
}

function populateSideOpeningChoices() {
  const rules = state.catalog?.side_openings || {};
  const sizeSelect = $("#side-opening-size");
  if (sizeSelect && !sizeSelect.options.length) {
    for (const choice of rules.sizes || []) {
      sizeSelect.add(new Option(choice.label, choice.value));
    }
  }
}

// Mirrors readEdgeMountForm/readLiftGrabberForm: only resets an *existing*
// key to defaults when off, so a design that never touched Side Openings
// keeps no key at all and design_to_dict omits the block while disabled.
// Fix 081 F: `changed` names which handle the caller actually just moved
// ("lower" or "upper"), so an illegal pair is walked back toward THAT edge.
// A caller with no specific handle in play (shape/size change, a side
// toggled, or a lid/stack change forcing a re-check) defaults to "lower",
// matching normalizeSideOpeningPair's own default. Previously this always
// hard-coded "upper" regardless of which handle the user had just dragged,
// which could silently move the wrong edge whenever the drag handler's own
// (correctly-directed) normalization disagreed with a fresh legality check.
function readSideOpeningForm(design, changed = "lower") {
  design.box = design.box || {};
  // Ordinary bins only - never surfaced for B4B or Base Trim.
  if (b4bEnabled() || baseTrimEnabled(design)) {
    if (design.box.side_openings) design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    return;
  }
  const sides = SIDE_OPENING_SIDE_IDS.filter(
    side => $(`#side-opening-${side}`)?.checked === true
  );
  const enabled = sides.length > 0 && !$("#side-openings-panel").hidden;
  if (!enabled) {
    if (design.box.side_openings) design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    return;
  }
  const current = { ...SIDE_OPENING_DEFAULTS, ...(design.box.side_openings || {}) };
  const shape = $("#side-opening-shape")?.value || current.shape;
  const pair = normalizeSideOpeningPair(design, sideOpeningPairFromControls(), changed);
  const fromBottom = pair.lower;
  const fromTop = 100 - pair.upper;
  const allowed = sideOpeningAllowedSizes({
    ...design,
    box: { ...design.box, side_openings: {
      ...current, sides, shape,
      from_bottom_percent: fromBottom, from_top_percent: fromTop,
    } },
  });
  let size = $("#side-opening-size")?.value || current.size;
  if (allowed.length && !allowed.includes(size)) size = allowed[allowed.length - 1];
  design.box.side_openings = {
    enabled: true,
    shape,
    sides,
    size,
    from_bottom_percent: fromBottom,
    from_top_percent: fromTop,
  };
  syncSideOpeningRange(design.box.side_openings);
}

function syncSideOpeningControls() {
  const active = sideOpeningPartActive();
  const forced = sideOpeningLidStackForced();
  if (forced) clampSideOpeningTopForLid(state.design, true);
  const so = sideOpeningState();
  $("#side-openings-panel").hidden = !active;
  $("#side-opening-shape").value = so.shape;
  syncSideOpeningRange(so);
  for (const side of SIDE_OPENING_SIDE_IDS) {
    const input = $(`#side-opening-${side}`);
    if (!input) continue;
    input.checked = (so.sides || []).includes(side);
    // Shared conditional-state explanation rule: a disabled wall choice
    // names its reason in its own label (Row B-15).
    const blockedReason = sideOpeningWallBlockedReason(side);
    input.disabled = Boolean(blockedReason);
    if (blockedReason) input.checked = false;
    const wallLabel = input.closest("label")?.querySelector("span");
    if (wallLabel) {
      wallLabel.textContent = blockedReason
        ? `${MODIFIER_SIDE_LABEL[side]} (${blockedReason})`
        : MODIFIER_SIDE_LABEL[side];
    }
  }
  const anyEligible = SIDE_OPENING_SIDE_IDS.some(side => sideOpeningEligibleSide(side));
  const allowed = sideOpeningAllowedSizes();
  const sizeSelect = $("#side-opening-size");
  if (sizeSelect) {
    for (const option of sizeSelect.options) option.disabled = !allowed.includes(option.value);
    if (allowed.length && !allowed.includes(sizeSelect.value)) {
      sizeSelect.value = allowed[allowed.length - 1];
      flashField(sizeSelect);
    } else {
      sizeSelect.value = so.size;
    }
  }
  const note = $("#side-opening-note");
  if (note) {
    if (!anyEligible) {
      const rules = state.catalog?.side_openings || {};
      note.textContent = `Side openings require at least one bin side to be 2 units (${fmt(number(rules.min_side_mm, 16))} mm) or longer.`;
    } else if (sideOpeningAdjustmentNote) {
      note.textContent = sideOpeningAdjustmentNote;
    } else if (forced) {
      note.textContent = "The upper handle stops below the rim to keep the Lid & Stacking bridge.";
    } else {
      note.textContent = "";
    }
  }
}

function wallPresetChoices(box = state.design?.box) {
  if (box?.b4b?.enabled) {
    const b4bChoices = state.catalog?.b4b_rules?.wall_choices;
    if (Array.isArray(b4bChoices) && b4bChoices.length) return b4bChoices;
  }
  const rules = state.catalog?.wall_rules || {};
  return Array.isArray(rules.choices) && rules.choices.length
    ? rules.choices
    : [
        { value: 0.4, label: "Very thin / prototype" },
        { value: 0.8, label: "Default" },
        { value: 1.2, label: "Strong" },
        { value: 1.6, label: "Heavy" },
        { value: 2.0, label: "Extra heavy" },
        { value: 2.4, label: "Maximum" },
      ];
}

function populateWallChoices(box, select = $("#wall-thickness")) {
  const isB4B = Boolean(box?.b4b?.enabled);
  const ordinaryRules = state.catalog?.wall_rules || {};
  const b4bRules = state.catalog?.b4b_rules || {};
  const stacking = (box?.stack?.mode || "none") === "direct" || Boolean(box?.lid?.enabled && box.lid.stackable);
  const hasLid = Boolean(box?.lid?.enabled);
  const stackMin = (stacking || hasLid) ? number(state.catalog?.stack_rules?.min_wall_mm, 1.2) : -Infinity;
  const modeMin = isB4B ? b4bMinWall() : stackMin;
  const choices = wallPresetChoices(box).filter(choice => number(choice.value) >= modeMin - 1e-9);
  const defaultWall = isB4B
    ? number(b4bRules.default_wall_mm, 1.6)
    : number(ordinaryRules.default_mm, 0.8);
  const wall = number(box?.wall, defaultWall);
  const value = fmt(wall);
  const standard = !isB4B && box?.standard_walls !== false && !stacking && !hasLid;
  const ordinaryDefaultValue = fmt(ordinaryRules.default_mm ?? 0.8);
  const numericChoices = isB4B
    ? choices
    : choices.filter(choice => fmt(choice.value) !== ordinaryDefaultValue);
  const isDiscrete = numericChoices.some(choice => fmt(choice.value) === value);
  const customValue = !standard && !isDiscrete ? value : "";
  const signature = JSON.stringify({ numericChoices, customValue, modeMin, standard });
  if (select.dataset.choices !== signature) {
    select.replaceChildren();
    if (!stacking && !hasLid && !isB4B) select.add(new Option("0.8 mm — Default", "standard"));
    select.append(...numericChoices.map(choice => new Option(
      `${number(choice.value).toFixed(1)} mm — ${choice.label}`,
      fmt(choice.value),
    )));
    if (customValue) {
      // A saved design keeps whatever wall it was made with: the preset list is
      // what a *new* choice may be, not a migration of existing geometry.
      select.add(new Option(`${customValue} mm — Existing`, customValue));
    }
    select.dataset.choices = signature;
  }
  select.value = standard ? "standard" : value;
  if (box?.standard_walls === false) select.dataset.customValue = value;
}

// Minimum base thickness depends on wall thickness (the foot's flare has to
// finish inside solid base material before the wall begins), so the browser
// carries a Python-generated table rather than one fixed number per mode. A
// wall that falls between table entries takes the NEXT THICKER wall's
// minimum - never the thinner one, which would under-report what the
// geometry actually needs.
function stackBaseMinForWall(mode, wall) {
  const table = state.catalog?.stack_rules?.base_min_by_wall_mm?.[mode];
  const fallback = mode === "direct" ? 3.8 : 1.8;
  const entries = Object.entries(table || {})
    .map(([w, v]) => ({ wall: number(w), min: number(v) }))
    .filter(entry => Number.isFinite(entry.wall) && Number.isFinite(entry.min))
    .sort((a, b) => a.wall - b.wall);
  if (!entries.length) return fallback;
  const wallValue = number(wall, entries[0].wall);
  for (const entry of entries) {
    if (wallValue <= entry.wall + 1e-9) return entry.min;
  }
  return entries[entries.length - 1].min;
}

// The base value a stacking mode *requires*, or -Infinity when nothing forces
// it.  Ordinary lid/direct stacking and B4B stacking are the only two things
// that do; the two never apply at once (B4B and ordinary stacking are
// mutually exclusive), so one helper covers both without a conflict.
function baseRequiredMin(box) {
  if (box?.b4b?.enabled) {
    return box.b4b.stacking
      ? number(state.catalog?.b4b_rules?.stack_min_base_mm, 2.8)
      : -Infinity;
  }
  const mode = (box?.stack?.mode || "none") === "direct"
    ? "direct" : box?.lid?.enabled && box.lid.stackable ? "lid" : "none";
  if (mode === "none") return -Infinity;
  return stackBaseMinForWall(mode, box?.wall);
}

function baseRequiredLabel(box) {
  if (box?.b4b?.enabled) return "Required for stacking";
  const mode = (box?.stack?.mode || "none") === "direct"
    ? "direct" : box?.lid?.enabled && box.lid.stackable ? "lid" : "none";
  if (mode === "direct") return "Required for direct stacking";
  if (mode === "lid") return "Required for lid stacking";
  return "";
}

function populateBaseChoices(box, select = $("#base-thickness")) {
  const isB4B = Boolean(box?.b4b?.enabled);
  const ordinaryRules = state.catalog?.base_rules || {};
  const b4bRules = state.catalog?.b4b_rules || {};
  const rules = isB4B
    ? {
        default_mm: number(b4bRules.default_base_mm, 1.6),
        choices: Array.isArray(b4bRules.base_choices)
          ? b4bRules.base_choices
          : [],
      }
    : ordinaryRules;
  const modeMin = baseRequiredMin(box);
  const allChoices = Array.isArray(rules.choices) && rules.choices.length
    ? rules.choices
    : [
        { value: 0.4, label: "Very thin" },
        { value: 0.6, label: "Good" },
        { value: 0.8, label: "Default" },
        { value: 1.0, label: "Extra heavy" },
        { value: 1.2, label: "Maximum" },
      ];
  // A mode floor above the highest preset (B4B's 2.8, ordinary direct's 3.8)
  // filters every ordinary preset out, which is the point: the control must
  // not sit at a base the geometry cannot use.
  const choices = allChoices.filter(choice => number(choice.value) >= modeMin - 1e-9);
  const requiredLabel = baseRequiredLabel(box);
  const needsRequiredOption = Number.isFinite(modeMin) && requiredLabel
    && !choices.some(choice => Math.abs(number(choice.value) - modeMin) < 1e-9);
  const base = number(box?.base_thickness, rules.default_mm ?? 0.8);
  const value = fmt(base);
  const verticalStack = (box?.stack?.mode || "none") === "direct" || Boolean(box?.lid?.enabled && box.lid.stackable);
  const standard = box?.standard_base !== false && !isB4B && !verticalStack;
  const ordinaryDefaultValue = fmt(ordinaryRules.default_mm ?? 0.8);
  const numericChoices = isB4B
    ? choices
    : choices.filter(choice => fmt(choice.value) !== ordinaryDefaultValue);
  const knownValues = numericChoices.map(choice => fmt(choice.value));
  if (needsRequiredOption) knownValues.push(fmt(modeMin));
  const customValue = !standard && !knownValues.includes(value) ? value : "";
  const signature = JSON.stringify({ numericChoices, needsRequiredOption, modeMin, customValue, standard });
  if (select.dataset.choices !== signature) {
    select.replaceChildren();
    if (!isB4B && !verticalStack) {
      select.add(new Option("Standard", "standard"));
    }
    select.append(...numericChoices.map(choice => new Option(
      `${number(choice.value).toFixed(1)} mm — ${choice.label}`,
      fmt(choice.value),
    )));
    if (needsRequiredOption) {
      select.add(new Option(`${fmt(modeMin)} mm — ${requiredLabel}`, fmt(modeMin)));
    }
    if (customValue) {
      // A saved design keeps whatever base it was made with: the preset list
      // is what a *new* choice may be, not a migration of existing geometry.
      select.add(new Option(`${customValue} mm — Existing`, customValue));
    }
    select.dataset.choices = signature;
  }
  select.value = standard ? "standard" : value;
}

function syncBaseControls() {
  $("#base-thickness-setting").hidden = isSurfaceBinDesign();
}

function syncWallControls() {
  const isB4B = b4bEnabled();
  const stacking = stackMode() !== "none" || Boolean(state.design?.box?.lid?.enabled);
  $("#wall-thickness-setting").hidden = false;
  const choices = wallPresetChoices(state.design?.box);
  const thinnest = choices.length ? number(choices[0].value, 0.4) : 0.4;
  const currentWall = number($("#wall-thickness").value, isB4B ? 1.6 : 0.8);
  const warningEl = $("#thin-wall-warning");
  if (warningEl) {
    const isThinnest = Math.abs(currentWall - thinnest) <= 1e-9;
    const hideWarning = (!isB4B && stacking) || $("#wall-thickness").value === "standard" || !isThinnest;
    warningEl.hidden = hideWarning;
    if (!hideWarning) {
      warningEl.textContent = isB4B
        ? "Super thin / light duty — reduced case strength."
        : "Very thin - may not print reliably with standard nozzle/slicer settings.";
    }
  }
}

function syncForm() {
  // Fix 060 Correction 3: syncForm() is also called for routine same-design
  // refreshes (modifier apply/rollback, Nest operations, preview auto-grow,
  // and more), not only when a different design is bound - so it must never
  // touch state.lidMemory itself. Real design-replacement call sites reseed
  // it explicitly via bindLidMemoryForDesign() before calling this.
  normalizeStackSettings(state.design);
  const { box, layout } = state.design;
  ensureRimFeatureInLayout();
  syncRimLabelFromFeatures();
  if (document.activeElement === $("#x-size")) {
    $("#x-size").value = fmt(box.x);
  } else {
    formatDimField("x");
  }
  if (document.activeElement === $("#y-size")) {
    $("#y-size").value = fmt(box.y);
  } else {
    formatDimField("y");
  }
  if (document.activeElement === $("#z")) {
    $("#z").value = fmt(box.z);
  } else {
    formatHeightField();
  }
  populateWallChoices(box);
  syncWallControls();
  populateBaseChoices(box);
  syncBaseControls();
  syncStackDependencyControls();
  populateLiftGrabberChoices();
  $("#lift-grabber-size").value = box.lift_grabbers?.enabled ? (box.lift_grabbers?.size || "medium") : "no";
  $("#lift-grabber-location").value = box.lift_grabbers?.location || "sides";
  syncLiftGrabberControls();
  if (editingEdgeMount()) syncEdgeMountControls();
  if (!state.design.part_name || !state.design.part_name.trim()) {
    const labelCandidate = state.design.label || state.design.b4b?.label_text || state.design.layout?.features?.find(f => f.kind === "text")?.options?.text;
    if (labelCandidate && !SIZE_LIKE_TEXT.test(labelCandidate)) {
      state.design.part_name = labelCandidate.trim();
    }
  }
  $("#part-name").value = state.design.part_name || "";
  $("#mode-select").value = layout.mode;
  $("#output-folder").value = state.runtime.hosted
    ? (state.browserFolder?.name || "Select a folder...")
    : state.output;
  // A routine form refresh must not touch the folder's inventory setting.
  setFolderState(
    state.folderMode,
    state.activeSpace,
    state.inventoryEnabled,
    state.keepBinDefaults,
    state.spaceBinDefaults,
    state.spacePartDefaults,
  );
  $("#connector-tolerance").value = fmt(state.connector.tolerance);
  $("#connector-length").value = fmt(state.connector.length);
  const armThicknessEl = $("#connector-arm-thickness");
  if (armThicknessEl) armThicknessEl.value = fmt(state.connector.arm_thickness ?? 1.0);
  $("#connector-bin-a-height").value = fmt(state.connector.bin_a_height ?? box.z);
  $("#connector-bin-b-height").value = fmt(state.connector.bin_b_height ?? box.z);
  $("#connector-height-mode").value = state.connector.different_heights ? "different" : "same";
  syncLidForm();
  populateSideOpeningChoices();
  syncSideOpeningControls();
  syncPegboardMountForm();
  syncConnectorSectionVisibility();
  updateInteriorModeVisibility();
  syncSurfaceControls();
  renderPlaced();
}

function activePegboardStandard() {
  const id = state.design?.box?.pegboard?.standard || state.activeSpace?.pegboard_standard || "standard";
  return state.catalog?.pegboard_rules?.standards?.find(row => row.id === id) || null;
}

function pegboardMinimumFor(count, standard, axis) {
  const sizes = axis === "x" ? standard?.minimum_widths_mm : standard?.minimum_heights_mm;
  return Number(sizes?.[count - 1] ?? Infinity);
}

function syncPegboardMountForm() {
  const row = $("#pegboard-mount-row");
  if (!row) return;
  const mount = state.design?.box?.pegboard;
  const active = Boolean(mount?.enabled) || (state.folderMode === "space" && state.activeSpace?.kind === "pegboard");
  row.hidden = !active || b4bEnabled() || baseTrimEnabled();
  if (row.hidden) return;
  const standard = activePegboardStandard();
  $("#pegboard-mount-standard").textContent = standard?.name || "Pegboard";
  $("#pegboard-cleat-x").value = String(mount?.cleat_x ?? "auto");
  $("#pegboard-cleat-y").value = String(mount?.cleat_y ?? "auto");
  for (const [selector, size, axis] of [["#pegboard-cleat-x", state.design.box.x, "x"], ["#pegboard-cleat-y", state.design.box.z, "y"]]) {
    for (const option of $(selector).options) {
      option.disabled = option.value !== "auto" && size + 1e-9 < pegboardMinimumFor(Number(option.value), standard, axis);
    }
    if ($(selector).selectedOptions[0]?.disabled) {
      $(selector).value = "auto";
      if (state.design.box.pegboard) state.design.box.pegboard[selector.endsWith("-x") ? "cleat_x" : "cleat_y"] = "auto";
    }
  }
  const preview = state.preview?.pegboard;
  const ribCount = preview?.ribs?.length || 0;
  $("#pegboard-mount-note").textContent = preview
    ? `${preview.resolved_x} × ${preview.resolved_y} receiver grid${ribCount ? `, ${ribCount} support rib${ribCount === 1 ? "" : "s"}` : ""}.`
    : "The receiver is standard-neutral; generation also creates the matching board adapters.";
}

function readPegboardMountForm(design) {
  design.box ||= {};
  const enabled = Boolean(design.box.pegboard?.enabled) ||
    (state.folderMode === "space" && state.activeSpace?.kind === "pegboard");
  if (!enabled || b4bEnabled(design) || baseTrimEnabled(design)) {
    if (design.box.pegboard) design.box.pegboard.enabled = false;
    return;
  }
  const standard = activePegboardStandard();
  const choice = (selector, size, axis) => {
    const value = $(selector)?.value || "auto";
    if (value === "auto" || size + 1e-9 >= pegboardMinimumFor(Number(value), standard, axis)) return value;
    $(selector).value = "auto";
    return "auto";
  };
  design.box.pegboard = {
    enabled: true,
    standard: design.box.pegboard?.standard || state.activeSpace?.pegboard_standard || "standard",
    cleat_x: choice("#pegboard-cleat-x", design.box.x, "x"),
    cleat_y: choice("#pegboard-cleat-y", design.box.z, "y"),
  };
}

function autoAdjustConnectorFields() {
  const rules = state.catalog?.connector_rules || {};
  const armT = rules.arm_thickness_mm ?? 1.0;
  const minDrop = rules.min_drop_mm ?? 2.0;
  const fullDrop = rules.full_drop_mm ?? 30.0;
  const webT = rules.web_thickness_mm ?? 3.0;
  const gain = rules.length_gain ?? 0.5;
  const baseLen = 12.0;

  const different = $("#connector-height-mode").value === "different";
  const binA = number($("#connector-bin-a-height").value, state.design?.box?.z ?? 40);
  const binB = different
    ? number($("#connector-bin-b-height").value, binA)
    : binA;
  const drop = different ? Math.abs(binA - binB) : 0;
  const frac = drop <= minDrop
    ? 0
    : Math.max(0, Math.min(1, (drop - minDrop) / (fullDrop - minDrop)));

  // Over the drop the seam holds one wall, not two, so the web has to reach
  // back across the empty half of the channel and run on the taller bin's
  // outer face. That reach is set by the seam, not by the drop, so it is a
  // floor under the drop-scaled thickness rather than a fraction of it - the
  // web is never thinner than this, however small the difference in height.
  const wallRules = state.catalog?.wall_rules || {};
  const wall = state.design?.box?.wall ?? wallRules.default_mm ?? 0.8;
  const tolerance = number($("#connector-tolerance")?.value, 0.02);
  const reach = wall * (wallRules.wall_depth_factor ?? rules.wall_depth_factor ?? 1.181)
    + (wallRules.mating_gap_mm ?? rules.mating_gap_mm ?? 0.25)
    + tolerance
    - (rules.web_run_clearance_mm ?? 0.15);

  const adjustedLen = baseLen * (1 + gain * frac);
  // frac === 0 is a plain extension with no web at all.
  const adjustedArm = frac > 0
    ? armT + Math.max((webT - armT) * frac, reach)
    : armT;

  const lenEl = $("#connector-length");
  if (lenEl && lenEl.value !== fmt(adjustedLen)) {
    lenEl.value = fmt(adjustedLen);
    flashField(lenEl);
  }
  const armEl = $("#connector-arm-thickness");
  if (armEl && armEl.value !== fmt(adjustedArm)) {
    armEl.value = fmt(adjustedArm);
    flashField(armEl);
  }
  if (state.connector) {
    state.connector.length = adjustedLen;
    state.connector.arm_thickness = adjustedArm;
  }
}

function syncConnectorHeightControls() {
  const different = $("#connector-height-mode").value === "different";
  $("#connector-bin-heights").hidden = !different;
  const settingsEl = $("#connector-settings");
  if (settingsEl) settingsEl.hidden = !different;
  autoAdjustConnectorFields();
  syncConnectorActionLabels();
}

// Mirrors organizer_engine.MIN_JOINABLE_SIZE; corner connectors below this
// in either X or Y are physically impossible regardless of user choice.
const MIN_CORNER_JOINABLE_MM = 16;

function syncConnectorSectionVisibility() {
  const noConnectors = baseTrimEnabled() || b4bEnabled();
  const heightWrap = $("#connector-height-wrap");
  if (noConnectors) {
    if (heightWrap) heightWrap.hidden = true;
    $("#connector-bin-heights").hidden = true;
    $("#connector-settings").hidden = true;
    renderConnectorReadout();
    $("#generate-all").hidden = true;
    $("#generate-connector").hidden = true;
    syncPrintChoiceAvailability();
    return;
  }
  // Fix 111 N10: lid-locked - the tuning controls hide and the section shows
  // a compact reason instead (renderConnectorReadout). Here
  // connectorsUnavailable() can only mean a lid, because b4b/baseTrim
  // returned above.
  const lidLocked = connectorsUnavailable();
  if (heightWrap) heightWrap.hidden = lidLocked;
  if (lidLocked) {
    $("#connector-bin-heights").hidden = true;
    $("#connector-settings").hidden = true;
  } else {
    syncConnectorHeightControls();
  }
  renderConnectorReadout();
  $("#generate-all").hidden = lidLocked;
  syncPrintChoiceAvailability();
  $("#generate-bin").hidden = false;
  $("#generate-connector").hidden = lidLocked;
  syncConnectorActionLabels();
}

// Fix 019 Item 7: same-height bins auto-bundle Side + 3-Way + 4-Way
// connectors; different-height bins only ever produce a Side connector -
// keep the action wording matching that actual bundle, on every
// syncForm()/height-mode change, not just at first render.
function syncConnectorActionLabels() {
  const allButton = $("#generate-all");
  const connectorButton = $("#generate-connector");
  if (!allButton && !connectorButton) return;
  const different = $("#connector-height-mode")?.value === "different";
  if (allButton) {
    allButton.textContent = different ? "Save Bin + Side Connector" : "Save Bin + Connectors";
  }
  if (connectorButton) {
    connectorButton.textContent = different ? "Save Side Connector" : "Save Connectors";
    connectorButton.title = different
      ? "Save the Side connector for the current bin"
      : "Save Side, 3-Way Corner, and 4-Way Corner connectors for the current bin";
  }
}

function renderConnectorReadout(plan = null) {
  const el = $("#connector-derived");
  if (!el) return;
  if (baseTrimEnabled() || b4bEnabled()) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  // Fix 111 N10: the compact reason for the lid lock - the one eligibility
  // contract, stated where the connector controls were. After the
  // b4b/baseTrim return above, connectorsUnavailable() here can only mean
  // a lid.
  if (connectorsUnavailable()) {
    el.textContent = "Side connectors aren't available with a lid.";
    el.hidden = false;
    return;
  }
  // Audit 006 J3: the readout is exception-only. An ordinary eligible
  // same-height bin gets no generic explanation - only a set that actually
  // changed (different heights, or too small for corners) earns a line.
  const different = plan
    ? Boolean(plan.different_heights)
    : $("#connector-height-mode").value === "different";
  if (different) {
    el.textContent = "Side connector only — corner connectors require equal-height bins.";
    el.hidden = false;
    return;
  }
  const x = Number(plan?.box_x_mm ?? state.design?.box?.x);
  const y = Number(plan?.box_y_mm ?? state.design?.box?.y);
  const cornersSkipped = Array.isArray(plan?.skipped_types) && plan.skipped_types.length > 0;
  const tooSmall = cornersSkipped
    || (Number.isFinite(x) && Number.isFinite(y) && (x < MIN_CORNER_JOINABLE_MM || y < MIN_CORNER_JOINABLE_MM));
  if (tooSmall) {
    el.textContent = `Side connector only — corner connectors need at least ${MIN_CORNER_JOINABLE_MM} mm in both X and Y.`;
    el.hidden = false;
    return;
  }
  el.textContent = "";
  el.hidden = true;
}

function updateInteriorModeVisibility(reveal = false) {
  const hasSupport = Boolean(state.draft || state.design?.layout?.features?.length);
  if (reveal && !hasSupport && state.design.layout.mode !== "fused") {
    state.design.layout.mode = "fused";
    $("#mode-select").value = "fused";
  }
}