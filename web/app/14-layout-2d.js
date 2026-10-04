"use strict";

function renderLayout2D() {
  if (!state.preview) return;
  state.layoutDimensionHandles = [];
  state.dividerSegmentHits = [];
  const canvas = $("#preview-2d");
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
  if (drawPendingNestTrace(context, width, height)) return;
  if (drawNestEditWorkspace(context, width, height)) return;
  const bounds = state.preview.layout_bounds;
  const worldWidth = bounds[2] - bounds[0], worldHeight = bounds[3] - bounds[1];
  const layoutYaw = (state.layoutOrientation === "topup" ? 0 : state.camera.yaw) * Math.PI / 180;
  const cosine = Math.cos(layoutYaw), sine = Math.sin(layoutYaw);
  // Match the 3D camera's top-down projection: as it turns, the 2D placement
  // view turns with it.  This makes on-screen drag directions agree between
  // the two views without changing the layout's actual world coordinates.
  const layoutWidth = Math.abs(cosine) * worldWidth + Math.abs(sine) * worldHeight;
  const layoutHeight = Math.abs(sine) * worldWidth + Math.abs(cosine) * worldHeight;
  const pad = Math.max(42, Math.min(width, height) * .08);
  const scale = Math.min((width - 2 * pad) / layoutWidth, (height - 2 * pad) / layoutHeight);
  const cx = (bounds[0] + bounds[2]) / 2, cy = (bounds[1] + bounds[3]) / 2;
  const toCanvas = ([x, y]) => {
    const dx = x - cx, dy = y - cy;
    return [width / 2 + (dx * cosine - dy * sine) * scale,
      height / 2 + (-dx * sine - dy * cosine) * scale];
  };
  const toWorld = ([x, y]) => {
    const horizontal = (x - width / 2) / scale, vertical = (y - height / 2) / scale;
    return [cx + horizontal * cosine - vertical * sine,
      cy - horizontal * sine - vertical * cosine];
  };
  state.layoutTransform = { toCanvas, toWorld, scale };
  const worldRect = zone => drawClosedPath(context, [
    [zone[0], zone[1]], [zone[2], zone[1]], [zone[2], zone[3]], [zone[0], zone[3]],
  ], toCanvas);
  const cavity = state.preview.cavity_outline;
  const cavityPath = new Path2D();
  if (cavity && cavity.length) {
    cavity.forEach((point, index) => {
      const p = toCanvas(point);
      index === 0 ? cavityPath.moveTo(p[0], p[1]) : cavityPath.lineTo(p[0], p[1]);
    });
    cavityPath.closePath();
  } else {
    const path = worldRect(bounds);
    cavityPath.addPath(path);
  }
  context.fillStyle = "#ffffff";
  context.strokeStyle = "#5e7f88";
  context.lineWidth = 2;
  context.fill(cavityPath);
  context.stroke(cavityPath);
  context.save();
  context.clip(cavityPath);
  const pitch = state.design.layout.mode === "cartridge" ? 8 : 1;
  if (pitch * scale >= 8) {
    context.strokeStyle = "rgba(55,96,105,.10)";
    context.lineWidth = 1;
    for (let x = bounds[0] + pitch; x < bounds[2] - 1e-8; x += pitch) {
      const p0 = toCanvas([x, bounds[1]]), p1 = toCanvas([x, bounds[3]]);
      context.beginPath(); context.moveTo(p0[0], p0[1]); context.lineTo(p1[0], p1[1]); context.stroke();
    }
    for (let y = bounds[1] + pitch; y < bounds[3] - 1e-8; y += pitch) {
      const p0 = toCanvas([bounds[0], y]), p1 = toCanvas([bounds[2], y]);
      context.beginPath(); context.moveTo(p0[0], p0[1]); context.lineTo(p1[0], p1[1]); context.stroke();
    }
  }
  context.restore();
  // The flat rectangle every non-full-span support must still stay inside,
  // drawn as a reference against the true wavy wall around it.
  context.strokeStyle = "rgba(94,127,136,.55)";
  context.lineWidth = 1;
  context.setLineDash([4, 3]);
  context.stroke(worldRect(bounds));
  context.setLineDash([]);
  for (const reserved of state.preview.customization_zones) {
    const reservedPath = worldRect(reserved.zone);
    const reservedCenter = toCanvas([(reserved.zone[0] + reserved.zone[2]) / 2, (reserved.zone[1] + reserved.zone[3]) / 2]);
    context.fillStyle = "rgba(201,95,88,.13)";
    context.strokeStyle = "rgba(164,68,61,.55)";
    context.setLineDash([5, 4]);
    context.fill(reservedPath);
    context.stroke(reservedPath);
    context.setLineDash([]);
    context.fillStyle = "#8f4540";
    context.font = '11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
    context.fillText(reserved.name, reservedCenter[0], reservedCenter[1]);
  }
  if (state.selected !== null) {
    const saved = state.design.layout.features[state.selected];
    const active = state.layoutDrag?.index === state.selected
      ? state.layoutDrag.feature
      : (state.draft?.kind === "nest" ? state.draft : saved);
    if (active?.kind === "nest" && isNestEditWorkspaceActive()) drawNestPhotoReference(context, active, toCanvas);
  }
  const invalid = new Set(state.preview.invalid_feature_indexes || []);
  layoutFeatures().forEach((feature, index) => {
    const zonePath = worldRect(feature.zone);
    const p1 = toCanvas([feature.zone[2], feature.zone[1]]);
    const zoneCenter = toCanvas([(feature.zone[0] + feature.zone[2]) / 2, (feature.zone[1] + feature.zone[3]) / 2]);
    const color = invalid.has(index) ? COLORS.invalid : kindColor(feature.kind);
    context.strokeStyle = index === state.selected ? "#176e91" : shade(color, .72);
    context.lineWidth = index === state.selected ? 3 : 1.2;
    if (feature.kind === "nest" && feature.contour) {
      const editingPoint = state.layoutDrag?.index === index && state.layoutDrag?.mode === "point";
      context.fillStyle = color + "35";
      for (const points of nestOccurrenceOutlines(feature,
        editingPoint ? null : state.preview.nest_soft_contours?.[index],
        state.preview.nest_occurrences?.[index])) {
        const outline = drawClosedPath(context, points, toCanvas);
        context.fill(outline); context.stroke(outline);
      }
      // A not-yet-accepted scan-tuning retrace draws dashed over the
      // accepted (solid) outline - see spec section 35.
      if (isNestEditWorkspaceActive() && index === state.selected && state.nestCandidateContour?.length) {
        const candidateWorld = state.nestCandidateContour.map(point => nestLocalToWorld(feature, point));
        const candidatePath = drawClosedPath(context, candidateWorld, toCanvas);
        context.save();
        context.strokeStyle = "rgba(255,255,255,.95)";
        context.lineWidth = 8;
        context.stroke(candidatePath);
        context.setLineDash([6, 4]);
        context.strokeStyle = "#007ca8";
        context.lineWidth = 4;
        context.stroke(candidatePath);
        context.restore();
      }
      // Informational-only indicators for the resolved finger-access plan -
      // a scoop footprint on Recessed, a notch location on Raised Wall.
      drawNestAccessIndicators(context, state.preview?.nest_access?.[index], toCanvas);
    } else {
      // A fused cradle, post or divider fills less of its zone than the zone
      // itself, and the rest is floor a neighbour may use. Fill what the part
      // really covers and leave the zone as a faint outline around it, so the
      // difference between "mine" and "just my handle" is visible.
      const covered = footprintWorld(feature, index);
      const coveredPath = covered && worldRect(covered);
      const coveredCenter = covered && toCanvas([(covered[0] + covered[2]) / 2, (covered[1] + covered[3]) / 2]);
      context.fillStyle = feature.kind === "text" ? color + "25" : color + "cc";
      context.fill(coveredPath || zonePath);
      if (covered) {
        context.stroke(coveredPath);
        context.save();
        context.globalAlpha = .45;
        context.setLineDash([4, 3]);
      }
      context.stroke(zonePath);
      if (covered) context.restore();
      if (feature.kind === "pocket") {
        const wall = number(feature.options?.wall, 1.6);
        const innerPath = worldRect([feature.zone[0] + wall, feature.zone[1] + wall, feature.zone[2] - wall, feature.zone[3] - wall]);
        context.save();
        context.fillStyle = "rgba(255, 255, 255, 0.4)";
        context.fill(innerPath);
        context.strokeStyle = shade(color, 0.5);
        context.lineWidth = 1;
        context.stroke(innerPath);
        context.restore();
      }
      if (feature.kind === "slot") {
        const wall = number(feature.options?.wall, 1.6);
        const along = feature.along || "x";
        const count = feature.count || 2;
        context.save();
        context.strokeStyle = shade(color, 0.4);
        context.lineWidth = 1;
        const [z0, z1, z2, z3] = feature.zone;
        if (along === "x") {
          const step = (z3 - z1 - 2 * wall) / Math.max(1, count);
          for (let s = 0; s < count; s++) {
            const y = z1 + wall + (s + 0.5) * step;
            const pt0 = toCanvas([z0 + wall, y]), pt1 = toCanvas([z2 - wall, y]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        } else {
          const step = (z2 - z0 - 2 * wall) / Math.max(1, count);
          for (let s = 0; s < count; s++) {
            const x = z0 + wall + (s + 0.5) * step;
            const pt0 = toCanvas([x, z1 + wall]), pt1 = toCanvas([x, z3 - wall]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        }
        context.restore();
      }
      if (feature.kind === "steps") {
        const along = feature.along || "x";
        const count = feature.count || 3;
        context.save();
        context.strokeStyle = shade(color, 0.4);
        context.lineWidth = 1;
        const [z0, z1, z2, z3] = feature.zone;
        if (along === "x") {
          const step = (z3 - z1) / Math.max(1, count);
          for (let s = 1; s < count; s++) {
            const y = z1 + s * step;
            const pt0 = toCanvas([z0, y]), pt1 = toCanvas([z2, y]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        } else {
          const step = (z2 - z0) / Math.max(1, count);
          for (let s = 1; s < count; s++) {
            const x = z0 + s * step;
            const pt0 = toCanvas([x, z1]), pt1 = toCanvas([x, z3]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        }
        context.restore();
      }
      if (feature.kind === "scoop") {
        const along = feature.along || "x";
        context.save();
        context.strokeStyle = shade(color, 0.4);
        context.lineWidth = 1;
        const [z0, z1, z2, z3] = feature.zone;
        const steps = [0.2, 0.45, 0.7, 0.9];
        if (along === "x") {
          for (const s of steps) {
            const y = z1 + (z3 - z1) * s;
            const pt0 = toCanvas([z0, y]), pt1 = toCanvas([z2, y]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        } else {
          for (const s of steps) {
            const x = z0 + (z2 - z0) * s;
            const pt0 = toCanvas([x, z1]), pt1 = toCanvas([x, z3]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        }
        context.restore();
      }
      if (feature.kind === "text") {
        const activeFeature = (index === state.selected && state.draft?.kind === "text") ? state.draft : feature;
        renderLayoutText(context, activeFeature, toCanvas, scale, false);
      } else if (feature.kind === "divider") {
        const activeFeature = (index === state.selected && state.draft?.kind === "divider") ? state.draft : feature;
        const opt = activeFeature.options || {};
        const slopeOn = opt.slope_base === true ||
          ["true", "1", "yes", "on"].includes(String(opt.slope_base).toLowerCase()) ||
          Number(opt.bottom_angle) !== 0;
        if (slopeOn) {
          const slopeZones = activeFeature.options?.compartment_spans?.length
            ? dividerCompartmentsClient(activeFeature).cells.map(cell => cell.zone)
            : [activeFeature.zone];
          for (const slopeZone of slopeZones) {
            context.save();
            context.clip(worldRect(slopeZone));
            context.strokeStyle = "#1f6b45";
            context.lineWidth = 1.8;
            context.globalAlpha = .78;
            const [sx0, sy0, sx1, sy1] = slopeZone;
            const span = Math.max(sx1 - sx0, sy1 - sy0);
            for (let mark = -span; mark <= span * 2; mark += 8) {
              const a = activeFeature.along === "y"
                ? toCanvas([sx0, sy0 + mark])
                : toCanvas([sx0 + mark, sy0]);
              const b = activeFeature.along === "y"
                ? toCanvas([sx1, sy1 + mark])
                : toCanvas([sx1 + mark, sy1]);
              context.beginPath(); context.moveTo(a[0], a[1]); context.lineTo(b[0], b[1]); context.stroke();
            }
            context.restore();
          }
        }
        if (opt.label_divisions && opt.division_labels) {
          renderDividerDivisionLabels(context, activeFeature, toCanvas, scale);
        } else {
          context.fillStyle = "rgba(20,36,42,.82)";
          context.font = '600 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
          context.textAlign = "center";
          context.textBaseline = "middle";
          const [tx, ty] = coveredCenter || zoneCenter;
          context.fillText(partInfo(feature.kind)?.title || feature.kind, tx, ty);
        }
      } else {
        context.fillStyle = "rgba(20,36,42,.82)";
        context.font = '600 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
        context.textAlign = "center";
        context.textBaseline = "middle";
        const [tx, ty] = coveredCenter || zoneCenter;
        context.fillText(partInfo(feature.kind)?.title || feature.kind, tx, ty);
      }
    }
    if (index === state.selected) {
      const resizable = Boolean(partInfo(feature.kind)?.flags?.size || feature.kind === "nest");
      if (resizable) {
        context.fillStyle = "#237fa6";
        context.strokeStyle = "white";
        context.lineWidth = 1;
        context.fillRect(p1[0] - 6, p1[1] - 6, 12, 12);
        context.strokeRect(p1[0] - 6, p1[1] - 6, 12, 12);
      }
      if (feature.kind === "nest" && feature.contour) {
        const top = toCanvas([(feature.zone[0] + feature.zone[2]) / 2, feature.zone[3]]);
        const rotate = toCanvas([(feature.zone[0] + feature.zone[2]) / 2, feature.zone[3] + 8]);
        context.strokeStyle = "#237fa6";
        context.beginPath(); context.moveTo(top[0], top[1]); context.lineTo(rotate[0], rotate[1]); context.stroke();
        context.fillStyle = "#237fa6";
        context.beginPath(); context.arc(rotate[0], rotate[1], 6, 0, Math.PI * 2); context.fill();
        context.strokeStyle = "white"; context.stroke();
        if (isNestEditWorkspaceActive()) drawNestContourHandles(context, feature, toCanvas);
      }
    }
  });
  if (state.draft) {
    const draftHasError = Boolean(state.preview.draft_error);
    const draftColor = draftHasError ? COLORS.invalid : DRAFT_HIGHLIGHT;
    const zone = state.draft.zone;
    const zonePath = worldRect(zone);
    context.fillStyle = draftColor;
    context.strokeStyle = draftColor;
    context.lineWidth = 2;
    context.setLineDash([6, 3]);
    if (state.draft.kind === "nest" && state.draft.contour) {
      const liveDraft = state.layoutDrag?.feature || state.draft;
      const softContour = state.layoutDrag?.mode === "point" ? null : state.preview.draft_soft_contour;
      context.fillStyle = draftColor + "18";
      context.strokeStyle = draftColor;
      for (const points of nestOccurrenceOutlines(liveDraft, softContour,
        state.preview.draft_nest_occurrences)) {
        const outline = drawClosedPath(context, points, toCanvas);
        context.fill(outline); context.stroke(outline);
      }
    } else if (state.draft.kind !== "nest") {
      // Same as a placed support: fill the floor it really covers, outline the
      // zone it lives in.
      const covered = state.preview.draft_footprint;
      if (covered) {
        const coveredPath = worldRect(covered);
        context.fill(coveredPath);
        context.stroke(coveredPath);
      } else {
        context.fill(zonePath);
      }
      context.stroke(zonePath);
      if (state.draft.kind === "pocket") {
        const wall = number(state.draft.options?.wall, state.draftResolvedOptions?.wall ?? 1.6);
        const innerPath = worldRect([zone[0] + wall, zone[1] + wall, zone[2] - wall, zone[3] - wall]);
        context.save();
        context.fillStyle = "rgba(255, 255, 255, 0.35)";
        context.fill(innerPath);
        context.strokeStyle = draftColor;
        context.lineWidth = 1;
        context.stroke(innerPath);
        context.restore();
      }
      if (state.draft.kind === "text" && state.selected === null) {
        renderLayoutText(context, state.draft, toCanvas, scale, true);
      }
    }
    context.setLineDash([]);
  }
  layoutFeatures().forEach((feature, index) => {
    if (feature.kind !== "divider") return;
    const activeFeature = index === state.selected && state.draft?.kind === "divider"
      ? state.draft : feature;
    renderDividerSegments(context, activeFeature, index, toCanvas);
  });
  const offsetOutside = (start, end) => {
    const middle = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
    const length = Math.max(1, Math.hypot(middle[0] - width / 2, middle[1] - height / 2));
    const dx = (middle[0] - width / 2) * 18 / length;
    const dy = (middle[1] - height / 2) * 18 / length;
    return [[start[0] + dx, start[1] + dy], [end[0] + dx, end[1] + dy]];
  };
  const widthLine = offsetOutside(toCanvas([bounds[0], bounds[3]]), toCanvas([bounds[2], bounds[3]]));
  const depthLine = offsetOutside(toCanvas([bounds[0], bounds[1]]), toCanvas([bounds[0], bounds[3]]));
  const displayBox = dimensionDragBoxOverride(state.design.box, "2d");
  drawDimensionGhost2D(context, toCanvas, bounds);
  drawDimensionLine(context, ...widthLine, `Width ${fmt(displayBox.x)} mm`, false, { axis: "x", value: displayBox.x });
  drawDimensionLine(context, ...depthLine, `Depth ${fmt(displayBox.y)} mm`, false, { axis: "y", value: displayBox.y });

  const binBottom = Math.max(...[
    toCanvas([bounds[0], bounds[1]])[1], toCanvas([bounds[2], bounds[1]])[1],
    toCanvas([bounds[2], bounds[3]])[1], toCanvas([bounds[0], bounds[3]])[1],
  ]);
  const hintY = Math.min(height - 15, Math.max(binBottom + 24, height - 24));
  context.save();
  context.textAlign = "center";
  context.textBaseline = "middle";
  if (state.nudgeFeedback) {
    const text = `Moved ${state.nudgeFeedback.amount}  (Arrow: 1 mm · Shift: 10 mm · Ctrl: 0.1 mm)`;
    context.font = '600 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
    const tw = context.measureText(text).width;
    context.fillStyle = "rgba(248, 250, 249, 0.94)";
    context.fillRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.strokeStyle = "#237fa6";
    context.lineWidth = 1;
    context.strokeRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.fillStyle = "#176e91";
    context.fillText(text, width / 2, hintY);
  } else {
    const text = "Use Arrow keys or drag to move";
    context.font = '11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
    const tw = context.measureText(text).width;
    context.fillStyle = "rgba(248, 250, 249, 0.88)";
    context.fillRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.strokeStyle = "rgba(94, 127, 136, 0.35)";
    context.lineWidth = 1;
    context.strokeRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.fillStyle = "#5e7f88";
    context.fillText(text, width / 2, hintY);
  }
  context.restore();
  updateNudgeUI();
}

function layoutPoint(event) {
  const rect = $("#preview-2d").getBoundingClientRect();
  return state.layoutTransform.toWorld([event.clientX - rect.left, event.clientY - rect.top]);
}

function hitFeature(world) {
  const features = state.design.layout.features;
  // Prioritize the currently selected feature using its live draft zone (with generous padding for text)
  if (state.selected !== null && state.selected < features.length) {
    const selIndex = state.selected;
    const feat = (state.draft && state.draft.kind === features[selIndex].kind) ? state.draft : features[selIndex];
    const zone = feat.zone;
    if (feat.kind === "nest" && feat.contour) {
      if (isNestEditWorkspaceActive() && hitNestContourPoint(feat, world) !== null) return selIndex;
      if (state.layoutTransform) {
        const cx = (zone[0] + zone[2]) / 2;
        const handles = [[zone[2], zone[1]], [cx, zone[3] + 8]];
        if (handles.some(point => Math.hypot(
          (world[0] - point[0]) * state.layoutTransform.scale,
          (world[1] - point[1]) * state.layoutTransform.scale,
        ) < 14)) return selIndex;
      }
      if (nestOccurrenceOutlines(feat, state.preview?.nest_soft_contours?.[selIndex],
          state.preview?.nest_occurrences?.[selIndex]).some(outline => pointInPolygon(world, outline))) return selIndex;
    } else {
      const pad = feat.kind === "text" ? 3.0 : 0;
      if (world[0] >= zone[0] - pad && world[0] <= zone[2] + pad &&
          world[1] >= zone[1] - pad && world[1] <= zone[3] + pad) {
        return selIndex;
      }
    }
  }

  for (let index = features.length - 1; index >= 0; index--) {
    if (index === state.selected) continue;
    const feat = features[index];
    const zone = feat.zone;
    if (feat.kind === "nest" && feat.contour) {
      if (nestOccurrenceOutlines(feat, state.preview?.nest_soft_contours?.[index],
          state.preview?.nest_occurrences?.[index]).some(outline => pointInPolygon(world, outline))) return index;
      continue;
    }
    const pad = feat.kind === "text" ? 3.0 : 0;
    if (world[0] >= zone[0] - pad && world[0] <= zone[2] + pad &&
        world[1] >= zone[1] - pad && world[1] <= zone[3] + pad) {
      return index;
    }
  }
  return null;
}

function dividerLabelsClient(feature) {
  let labels = feature.options?.division_labels;
  if (typeof labels === "string") {
    try { labels = JSON.parse(labels); } catch { labels = labels.split(","); }
  }
  return Array.isArray(labels) ? [...labels] : [];
}

function promoteMergedDividerLabel(feature, merged, columns) {
  const labels = dividerLabelsClient(feature);
  const anchor = merged.row * columns + merged.column;
  if (String(labels[anchor] || "").trim()) return;
  const values = new Set();
  for (let row = merged.row; row < merged.row + merged.rowSpan; row++) {
    for (let column = merged.column; column < merged.column + merged.columnSpan; column++) {
      const text = String(labels[row * columns + column] || "").trim();
      if (text) values.add(text);
    }
  }
  if (values.size === 1) {
    labels[anchor] = [...values][0];
    feature.options.division_labels = labels;
  }
}

async function editDividerSegment(originalHit) {
  if (dividerLockedByLidLabels()) {
    toast(dividerLockMessage(), true, 6500);
    return;
  }
  if (state.dividerTopologyBusy) return;
  state.dividerTopologyBusy = true;
  try {
    if (state.selected !== originalHit.featureIndex) {
      await selectedFeature(originalHit.featureIndex);
    }
    if (state.selected !== originalHit.featureIndex || state.draft?.kind !== "divider") return;
    const topology = dividerCompartmentsClient(state.draft);
    const currentHit = dividerBoundarySegmentsClient(
      state.draft, originalHit.featureIndex, point => point,
    ).find(hit => hit.orientation === originalHit.orientation &&
      hit.line === originalHit.line && hit.segment === originalHit.segment);
    if (!currentHit) return;
    if (currentHit.action === "blocked") {
      state.dividerSegmentHover = originalHit;
      updateNudgeUI();
      toast("That merge would make an irregular compartment. Compartments must stay rectangular.");
      return;
    }

    let cells;
    if (currentHit.action === "merge") {
      cells = topology.cells.filter(cell =>
        !sameDividerCompartmentClient(cell, currentHit.a) &&
        !sameDividerCompartmentClient(cell, currentHit.b));
      cells.push(currentHit.merged);
      promoteMergedDividerLabel(state.draft, currentHit.merged, topology.columns);
    } else {
      const owner = currentHit.a;
      cells = topology.cells.filter(cell => !sameDividerCompartmentClient(cell, owner));
      if (currentHit.orientation === "vertical") {
        const leftWidth = currentHit.line - owner.column;
        cells.push(
          { row: owner.row, column: owner.column, rowSpan: owner.rowSpan, columnSpan: leftWidth },
          { row: owner.row, column: currentHit.line, rowSpan: owner.rowSpan, columnSpan: owner.columnSpan - leftWidth },
        );
      } else {
        const lowHeight = currentHit.line - owner.row;
        cells.push(
          { row: owner.row, column: owner.column, rowSpan: lowHeight, columnSpan: owner.columnSpan },
          { row: currentHit.line, column: owner.column, rowSpan: owner.rowSpan - lowHeight, columnSpan: owner.columnSpan },
        );
      }
    }

    refreshDraftSoon.cancel();
    state.draft.options ||= {};
    state.draft.options.compartment_spans = serializeDividerSpansClient(cells);
    state.draftAutoCommit = true;
    state.dividerSegmentHover = null;
    markDraftChanged();
    renderDraftFields();
    renderLayout2D();
    await refreshDraft();
  } finally {
    state.dividerTopologyBusy = false;
  }
}

function wireLayoutInteraction() {
  const canvas = $("#preview-2d");
  // Tracks whether the pointer is still down after an awaited "keep this part?"
  // prompt - if the user lifted their finger to answer it, there's no drag.
  let pointerActive = false;
  canvas.addEventListener("pointercancel", () => {
    pointerActive = false;
    if (state.dimensionDrag?.view === "2d") {
      cancelDimensionDrag(canvas);
      renderLayout2D();
    }
  });
  canvas.addEventListener("pointerdown", async event => {
    if (!state.layoutTransform || state.designMutationBusy || state.dividerTopologyBusy) return;
    // A dimension label always wins over ordinary feature selection/move/
    // resize - hit-test it first (see fix3d.md, item 5).
    const handle = hitDimensionHandle("2d", canvasPointFromEvent(canvas, event));
    if (handle) {
      beginDimensionDrag("2d", handle, canvas, event);
      renderLayout2D();
      return;
    }
    const dividerHit = hitDividerSegment(canvasPointFromEvent(canvas, event));
    if (dividerHit) {
      pointerActive = false;
      state.layoutDrag = null;
      await editDividerSegment(dividerHit);
      return;
    }
    pointerActive = true;
    const world = layoutPoint(event);
    let index = hitFeature(world);
    // In the dedicated outline editor, a click that misses the outline/photo
    // pans the view instead of deselecting - there is nothing else on this
    // canvas to click, so a miss is never "click away to close".
    if (index === null && isNestEditWorkspaceActive()) {
      pointerActive = false;
      state.layoutDrag = {
        mode: "pan",
        startCanvas: canvasPointFromEvent(canvas, event),
        startPanX: state.nestViewPanX,
        startPanY: state.nestViewPanY,
      };
      try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
      return;
    }
    if (index === null) {
      if (state.selected !== null) {
        if (!(await guardDraftSwitch())) return;
        resetNestPhotoSession();
        state.selected = null;
        state.draft = null;
        state.draftKind = null;
        $(".support-editor").hidden = true;
      }
      state.layoutDrag = null;
      state.nudgeFeedback = null;
      updateNudgeUI();
      renderPlaced(); updateSelectionButtons(); renderLayout2D();
      return;
    }
    if (index !== state.selected) {
      // May put up the "keep this part?" dialog before the selection moves.
      await selectedFeature(index);
      if (state.selected !== index) return;   // user chose to keep editing
      if (!pointerActive) return;             // finger already lifted for the dialog
    } else {
      cancelPendingDraftWork();
    }
    // A field edit may still exist only in the live draft. Start the drag from
    // exactly what is on screen, not the last server-saved copy, or moving the
    // same part immediately after typing can silently restore its old values.
    const feature = clone(
      state.selected === index && state.draft
        ? state.draft
        : state.design.layout.features[index]
    );
    if (feature.kind === "divider" && dividerLockedByLidLabels()) {
      pointerActive = false;
      toast(dividerLockMessage(), true, 6500);
      return;
    }
    if (feature.kind === "text") {
      pointerActive = false;
      return; // Text is selected here; its position is derived from its type.
    }
    if (feature.kind === "nest" && feature.contour && isNestEditWorkspaceActive()
        && (state.nestOutlineTool === "add-point" || state.nestOutlineTool === "delete-point")) {
      pointerActive = false;
      if (state.nestOutlineTool === "add-point") {
        const hit = hitNestContourSegment(feature, world);
        if (hit) {
          const contour = feature.contour.map(point => [...point]);
          contour.splice(hit.index + 1, 0, hit.local);
          await commitNestContourEdit(index, contour);
        }
      } else {
        const pointIndex = hitNestContourPoint(feature, world);
        if (pointIndex !== null && feature.contour.length > 3) {
          const contour = feature.contour.filter((_point, i) => i !== pointIndex);
          await commitNestContourEdit(index, contour);
        } else if (pointIndex !== null) {
          toast("A Photo Nest outline needs at least three points.", true);
        }
      }
      return;
    }
    // The dedicated outline editor never moves, rotates or resizes the part
    // itself - Select/Edit only drags an actual contour point; anything else,
    // including a click inside the filled outline, pans the viewport instead.
    if (isNestEditWorkspaceActive()) {
      const contourPoint = hitNestContourPoint(feature, world);
      if (contourPoint === null) {
        pointerActive = false;
        state.layoutDrag = {
          mode: "pan",
          startCanvas: canvasPointFromEvent(canvas, event),
          startPanX: state.nestViewPanX,
          startPanY: state.nestViewPanY,
        };
        try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
        return;
      }
      state.layoutDrag = {
        index, feature, original: clone(feature),
        mode: "point",
        contourPoint,
        photoBounds: state.nestPhoto?.bounds ? [...state.nestPhoto.bounds] : null,
        start: world,
        centre: [(feature.zone[0] + feature.zone[2]) / 2, (feature.zone[1] + feature.zone[3]) / 2],
        startAngle: 0,
        startRadius: 1,
      };
      try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
      return;
    }
    const zone = feature.zone;
    const handlePixels = Math.hypot((world[0] - zone[2]) * state.layoutTransform.scale, (world[1] - zone[1]) * state.layoutTransform.scale);
    const rotatePoint = [(zone[0] + zone[2]) / 2, zone[3] + 8];
    const rotatePixels = Math.hypot((world[0] - rotatePoint[0]) * state.layoutTransform.scale, (world[1] - rotatePoint[1]) * state.layoutTransform.scale);
    const centre = [(zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2];
    const resizable = Boolean(partInfo(feature.kind)?.flags?.size || feature.kind === "nest");
    const contourPoint = feature.kind === "nest" && isNestEditWorkspaceActive()
      ? hitNestContourPoint(feature, world) : null;
    state.layoutDrag = {
      index, feature, original: clone(feature),
      mode: contourPoint !== null ? "point"
        : feature.kind === "nest" && rotatePixels < 14 ? "rotate"
          : (resizable && handlePixels < 14) ? "resize" : "move",
      contourPoint,
      photoBounds: state.nestPhoto?.bounds ? [...state.nestPhoto.bounds] : null,
      start: world,
      centre,
      startAngle: Math.atan2(world[1] - centre[1], world[0] - centre[0]),
      startRadius: Math.max(.01, Math.hypot(world[0] - centre[0], world[1] - centre[1])),
    };
    try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
  });
  canvas.addEventListener("pointermove", event => {
    if (state.dimensionDrag?.view === "2d") {
      updateDimensionDrag(event.clientX, event.clientY);
      renderLayout2D();
      return;
    }
    if (!state.layoutDrag) {
      const handle = state.layoutTransform ? hitDimensionHandle("2d", canvasPointFromEvent(canvas, event)) : null;
      if (handle) {
        state.dividerSegmentHover = null;
        if (updateDimensionHover("2d", handle, canvas)) renderLayout2D();
        return;
      }
      updateDimensionHover("2d", null, canvas);
      const dividerHit = hitDividerSegment(canvasPointFromEvent(canvas, event));
      if (!sameDividerHit(dividerHit, state.dividerSegmentHover)) {
        state.dividerSegmentHover = dividerHit;
        canvas.style.cursor = dividerHit?.action === "blocked" ? "not-allowed" : dividerHit ? "pointer" : "";
        renderLayout2D();
      }
      return;
    }
    const drag = state.layoutDrag;
    if (!drag || !state.layoutTransform) return;
    if (drag.mode === "pan") {
      const point = canvasPointFromEvent(canvas, event);
      state.nestViewPanX = drag.startPanX + (point[0] - drag.startCanvas[0]);
      state.nestViewPanY = drag.startPanY + (point[1] - drag.startCanvas[1]);
      renderLayout2D();
      return;
    }
    const world = layoutPoint(event);
    const pitch = state.design.layout.mode === "cartridge" ? 8 : 1;
    const snap = value => Math.round(value / pitch) * pitch;
    const original = drag.original.zone;
    if (drag.mode === "point") {
      drag.feature.contour[drag.contourPoint] = nestWorldToLocal(drag.feature, world);
      normalizeNestContour(drag.feature);
    } else if (drag.mode === "move") {
      const width = original[2] - original[0], depth = original[3] - original[1];
      const cx = snap(drag.centre[0] + world[0] - drag.start[0]);
      const cy = snap(drag.centre[1] + world[1] - drag.start[1]);
      drag.feature.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
    } else if (drag.feature.kind === "nest" && drag.mode === "rotate") {
      const angle = Math.atan2(world[1] - drag.centre[1], world[0] - drag.centre[0]);
      const raw = number(drag.original.rotation) + (angle - drag.startAngle) * 180 / Math.PI;
      drag.feature.rotation = ((Math.round(raw / 90) * 90) % 360 + 360) % 360;
    } else if (drag.feature.kind === "nest") {
      const radius = Math.hypot(world[0] - drag.centre[0], world[1] - drag.centre[1]);
      drag.feature.scale = Math.max(.1, number(drag.original.scale, 1) * radius / drag.startRadius);
    } else {
      const width = Math.max(pitch, snap(2 * Math.abs(world[0] - drag.centre[0])));
      const depth = Math.max(pitch, snap(2 * Math.abs(world[1] - drag.centre[1])));
      drag.feature.zone = [drag.centre[0] - width / 2, drag.centre[1] - depth / 2, drag.centre[0] + width / 2, drag.centre[1] + depth / 2];
    }
    renderLayout2D();
  });
  canvas.addEventListener("pointerleave", () => {
    if (state.layoutDrag || state.dimensionDrag?.view === "2d") return;
    if (state.dividerSegmentHover) {
      state.dividerSegmentHover = null;
      canvas.style.cursor = "";
      renderLayout2D();
    }
  });
  canvas.addEventListener("pointerup", async event => {
    pointerActive = false;
    if (state.dimensionDrag?.view === "2d") {
      commitDimensionDrag(canvas);
      renderLayout2D();
      return;
    }
    const drag = state.layoutDrag;
    if (!drag) return;
    state.layoutDrag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (typeof drag.index !== "number") return;   // not a feature drag - nothing to apply
    state.draft = drag.feature;
    if (drag.mode === "move" && drag.feature.kind === "nest" && drag.feature.options?.auto_size === true
        && state.design.layout.features.filter(one => one.kind === "nest").length === 1) {
      const zone = drag.feature.zone;
      const cx = (zone[0] + zone[2]) / 2, cy = (zone[1] + zone[3]) / 2;
      if (Math.abs(cx) > 0.5 || Math.abs(cy) > 0.5) {
        drag.feature.options.auto_size = false;
        toast("Automatic footprint sizing turned off because the bin size or layout was manually changed.");
      }
    }
    if (drag.mode === "resize" && drag.feature.kind !== "nest") {
      // Resizing by the blue corner is just as intentional as typing Width or
      // Length. Preserve both axes from later contents-driven auto fitting.
      pinDraftAxis("width");
      pinDraftAxis("depth");
      state.partZoneLocks[drag.index] = state.pinnedZone;
    }
    const applied = await applySupport(drag.index);
    if (!applied) {
      if (drag.photoBounds && state.nestPhoto) state.nestPhoto.bounds = drag.photoBounds;
      state.draft = clone(state.design.layout.features[drag.index]);
      renderDraftFields();
      refreshDraft();
      renderLayout2D();
    }
  });
  window.addEventListener("keydown", handleLayoutArrowKeys);
}

function handleLayoutArrowKeys(event) {
  const arrowKeys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
  if (!arrowKeys.includes(event.key)) return;

  const is2D = $(".canvas-wrap[data-canvas='2d']")?.classList.contains("active");
  if (!is2D) return;

  const inField = Boolean(
    event.target.closest("input, textarea, select, [contenteditable='true'], .view-tab") ||
    document.activeElement?.closest("input, textarea, select, [contenteditable='true'], .view-tab")
  );
  if (inField) return;

  if (document.querySelector("dialog[open], .modal.active")) return;
  if (state.selected === null || !state.design?.layout?.features?.[state.selected]) return;

  event.preventDefault();

  let step = 1;
  let mod = "normal";
  if (event.ctrlKey || event.metaKey) {
    step = 0.1;
    mod = "ctrl";
  } else if (event.shiftKey) {
    step = 10;
    mod = "shift";
  }

  let dx = 0, dy = 0;
  if (event.key === "ArrowLeft") dx = -step;
  else if (event.key === "ArrowRight") dx = step;
  else if (event.key === "ArrowUp") dy = step;
  else if (event.key === "ArrowDown") dy = -step;

  if (!state.draft) {
    state.draft = clone(state.design.layout.features[state.selected]);
    state.draftAutoCommit = true;
  }
  const feature = state.draft;
  if (feature.kind === "text") return;
  if (feature.kind === "divider" && dividerLockedByLidLabels()) {
    toast(dividerLockMessage(), true, 6500);
    return;
  }
  if (!pendingNudgeDraft) {
    pendingNudgeDraft = clone(state.draft);
  }
  const request = ++state.draftRequest;
  const z = feature.zone;
  const roundCoord = val => Math.round(val * 1000) / 1000;
  feature.zone = [
    roundCoord(z[0] + dx),
    roundCoord(z[1] + dy),
    roundCoord(z[2] + dx),
    roundCoord(z[3] + dy),
  ];

  if (feature.kind === "nest") {
    if (feature.options?.auto_size === true
        && state.design.layout.features.filter(one => one.kind === "nest").length === 1) {
      const cx = (feature.zone[0] + feature.zone[2]) / 2, cy = (feature.zone[1] + feature.zone[3]) / 2;
      if (Math.abs(cx) > 0.5 || Math.abs(cy) > 0.5) {
        feature.options.auto_size = false;
        toast("Automatic footprint sizing turned off because the bin size or layout was manually changed.");
      }
    }
  }

  state.nudgeFeedback = {
    amount: `${step} mm`,
    mod,
  };
  updateNudgeUI();
  renderLayout2D();

  commitNudge(request);
}

async function saveDesign() {
  // Ordinary output entry points defensively reject structural ownership:
  // a Storage Box or Storage Drawers target has its own Save/Print chrome.
  if (designTargetIsStructural()) {
    toast("These outputs are for ordinary bins. The structural editor has its own Save and Print actions.", true);
    return;
  }
  if (relocationBlocksWrites()) return;
  if (typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave())) return;
  if (!beginDesignMutation()) return;
  try {
    // The editor saves valid part edits after a short typing pause. Commit the
    // visible draft explicitly so an immediate Save cannot download the older
    // server copy while the new value is still waiting in that pause.
    await commitVisibleDraft();
    updateDesignFromForm();
    const body = JSON.stringify(state.design, null, 2) + "\n";
    const blob = new Blob([body], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${(state.design.part_name || "Wavefinity design").replace(/[^a-z0-9 _-]/gi, "").trim() || "Wavefinity design"}.wavefinity.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    state.cleanDesign = clone(state.design);
    toast("Design downloaded.");
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    finishDesignMutation();
  }
}

// The design as the form currently shows it, without touching state.design.
function visibleDesignSnapshot() {
  const visibleDesign = clone(state.design);
  visibleDesign.box.x = normalizeBinDimension("x", $("#x-size").value, visibleDesign.box.x);
  visibleDesign.box.y = normalizeBinDimension("y", $("#y-size").value, visibleDesign.box.y);
  visibleDesign.box.z = number($("#z").value, visibleDesign.box.z);
  if (isSurfaceBinDesign(visibleDesign) &&
      resolveSurfaceBase(visibleDesign, { fromForm: true }) === false) {
    throw new Error("Enter a positive Object height, or leave it blank.");
  }
  const defaultBase = number(state.catalog?.base_rules?.default_mm, 0.8);
  if (!isSurfaceBinDesign(visibleDesign)) {
    visibleDesign.box.standard_base = $("#base-thickness").value === "standard";
    visibleDesign.box.base_thickness = visibleDesign.box.standard_base
      ? defaultBase
      : number($("#base-thickness").value, visibleDesign.box.base_thickness ?? defaultBase);
  }
  const wallRules = state.catalog?.wall_rules || {};
  const defaultWall = wallRules.default_mm ?? 0.8;
  visibleDesign.box.standard_walls = $("#wall-thickness").value === "standard";
  visibleDesign.box.wall = visibleDesign.box.standard_walls
    ? defaultWall
    : Math.max(wallRules.min_mm ?? 0.2, Math.min(
        wallRules.max_mm ?? 2.4,
        number($("#wall-thickness").value, visibleDesign.box.wall ?? defaultWall),
      ));
  visibleDesign.part_name = $("#part-name").value;
  readStackForm(visibleDesign);
  normalizeStackSettings(visibleDesign);
  if (isSurfaceBinDesign(visibleDesign) && surfaceStackingBlocked(visibleDesign))
    visibleDesign.layout.surface_lightweight_base = false;
  readLiftGrabberForm(visibleDesign);
  if (editingEdgeMount()) readEdgeMountForm(visibleDesign);
  readSideOpeningForm(visibleDesign);
  return visibleDesign;
}

function designHasChanges() {
  if (designTargetIsStructural()) return false; // Fix 103
  const visibleDesign = visibleDesignSnapshot();
  const index = draftCommitIndex();
  if (state.draft && state.draftAutoCommit && (
    index === null ||
    (Number.isInteger(index) &&
      JSON.stringify(state.draft) !== JSON.stringify(state.design.layout.features[index]))
  )) return true;
  return JSON.stringify(visibleDesign) !== JSON.stringify(state.cleanDesign);
}

async function openDesign(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) {
    event.target.value = "";
    return;
  }
  if (designHasChanges() && !(await appConfirmAction({
    title: "Open a different design?",
    message: "Open this design and replace the current one? Unsaved changes to the current design will be lost.",
    actionLabel: "Open Design",
  }))) {
    event.target.value = "";
    return;
  }
  if (!beginDesignMutation()) return;
  try {
    const parsed = JSON.parse(await file.text());
    const result = await api("/api/design/validate", { design: parsed });
    if (isStructuralDesign(result.design)) {
      throw new Error("A Storage Box or Base Trim is saved from its Space, not opened in the Designer.");
    }
    state.design = result.design;
    clearDesignerHistory();
    resetNestPhotoSession();
    state.cleanDesign = clone(state.design);
    state.spaceStarterPreviewPending = false;
    if (state.folderMode === "space") state.designInventoryId = null;
    state.designTarget = null; // Fix 103
    state.drafts = {};
    state.binResizePending = false;
    state.binFootprintResizePending = false;
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection();
    await refreshPreview();
    if (typedSpaceOrdinaryBin()) await persistSpaceDesignSource(null, true);
    toast(`Opened ${file.name}.`);
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    event.target.value = "";
    finishDesignMutation();
  }
}

async function newDesign() {
  if (typedSpaceOrdinaryBin()) return designerNewBin();
  if (designHasChanges() && !(await appConfirmAction({
    title: "Start a new design?",
    message: "Start a new design and discard the current changes?",
    actionLabel: "Discard Changes",
    danger: true,
  }))) return;
  if (!beginDesignMutation()) return;
  state.design = freshDesignForCurrentFolder();
  clearDesignerHistory();
  state.surfaceHeightPromptSkipped = false;
  resetNestPhotoSession();
  state.cleanDesign = clone(state.design);
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  state.drafts = {};
  bindLidMemoryForDesign();
  syncForm();
  try {
    clearDraftSelection();
    await refreshPreview();
  } finally {
    finishDesignMutation();
  }
}

let isGenerating = false;

function wireGenerationDialog() {
  const dialog = $("#generation-dialog");
  const closeBtn = $("#generation-dialog-close");
  if (!dialog) return;
  dialog.addEventListener("cancel", (event) => {
    if (isGenerating) {
      event.preventDefault();
    }
  });
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      dialog.close();
    });
  }
}

function getIndicatorHtml(status) {
  if (status === "generating") {
    return `<span class="gen-spinner" aria-label="Saving"></span>`;
  }
  if (status === "done") {
    return `<span class="gen-status-icon done" aria-label="Done">✓</span>`;
  }
  if (status === "error") {
    return `<span class="gen-status-icon error" aria-label="Failed">✕</span>`;
  }
  return `<span class="gen-status-icon waiting" aria-label="Waiting">⋯</span>`;
}

function renderGenerationItems(items) {
  const container = $("#generation-items");
  if (!container) return;
  container.innerHTML = items.map(item => `
    <div class="generation-item status-${item.status}" id="gen-item-${item.id}">
      <div class="gen-item-indicator">
        ${getIndicatorHtml(item.status)}
      </div>
      <div class="gen-item-details">
        <strong class="gen-item-title">${escapeHtml(item.title)}</strong>
        <span class="gen-item-status">${escapeHtml(item.text)}</span>
      </div>
    </div>
  `).join("");
}

function setItemStatus(id, status, text) {
  const row = $(`#gen-item-${id}`);
  if (!row) return;
  row.className = `generation-item status-${status}`;
  const indicator = row.querySelector(".gen-item-indicator");
  if (indicator) indicator.innerHTML = getIndicatorHtml(status);
  const statusSpan = row.querySelector(".gen-item-status");
  if (statusSpan) statusSpan.textContent = text;
}

function showBinNameRequiredDialog(title, message) {
  const dialog = $("#bin-name-dialog");
  const partInput = $("#part-name");
  const titleEl = $("#bin-name-dialog-title");
  const messageEl = $("#bin-name-dialog-message");
  if (titleEl) titleEl.textContent = title || "Bins must have a name";
  if (messageEl) messageEl.textContent = message || "Bins must have a name before you can save or print.";
  if (!dialog || typeof dialog.showModal !== "function") {
    alert(message || "Bins must have a name");
    if (partInput) {
      partInput.focus();
      partInput.select();
    }
    return;
  }
  const onDone = () => {
    if (partInput) {
      partInput.focus();
      partInput.select();
    }
  };
  dialog.addEventListener("close", onDone, { once: true });
  if (!dialog.open) {
    dialog.showModal();
    $("#bin-name-dialog-ok")?.focus();
  }
}

function showFilenameConflictDialog(names, renameHint = "Please label the bin with a different name, then save again.") {
  const list = names.join(", ");
  showBinNameRequiredDialog(
    "This name is already used",
    `A file named "${list}" already exists in your chosen folder. ${renameHint}`
  );
}

// Connector files cannot be fixed by renaming a bin, so a differing same-name
// connector file gets an explicit Replace / Cancel choice.
function confirmReplaceConnectorFiles(names) {
  return new Promise(resolve => {
    const dialog = document.createElement("dialog");
    dialog.className = "wf-confirm-dialog";
    const title = document.createElement("h3");
    title.textContent = "Replace existing connector file(s)?";
    const body = document.createElement("p");
    body.textContent = "These connector files already exist in your folder with different contents:";
    const list = document.createElement("ul");
    for (const name of names) { const li = document.createElement("li"); li.textContent = name; list.append(li); }
    const actions = document.createElement("div");
    actions.className = "button-row";
    const replace = document.createElement("button");
    replace.type = "button"; replace.textContent = "Replace"; replace.className = "button danger";
    const cancel = document.createElement("button");
    cancel.type = "button"; cancel.textContent = "Cancel"; cancel.className = "button secondary";
    let answer = false;
    replace.addEventListener("click", () => { answer = true; dialog.close(); });
    cancel.addEventListener("click", () => dialog.close());
    actions.append(cancel, replace);
    dialog.append(title, body, list, actions);
    dialog.addEventListener("close", () => { dialog.remove(); resolve(answer); }, { once: true });
    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
  });
}

// A differing same-name file that is not proven Wavefinity-owned gets an
// explicit Replace / Cancel choice instead of a hard rename demand.
function confirmReplaceOutputFiles(names, what) {
  return new Promise(resolve => {
    const dialog = document.createElement("dialog");
    dialog.className = "wf-confirm-dialog";
    const title = document.createElement("h3");
    title.textContent = `Replace existing ${what} file(s)?`;
    const body = document.createElement("p");
    body.textContent = `These ${what} files already exist in your folder with different contents:`;
    const list = document.createElement("ul");
    for (const name of names) { const li = document.createElement("li"); li.textContent = name; list.append(li); }
    const actions = document.createElement("div");
    actions.className = "button-row";
    const replace = document.createElement("button");
    replace.type = "button"; replace.textContent = "Replace"; replace.className = "button danger";
    const cancel = document.createElement("button");
    cancel.type = "button"; cancel.textContent = "Cancel"; cancel.className = "button secondary";
    let answer = false;
    replace.addEventListener("click", () => { answer = true; dialog.close(); });
    cancel.addEventListener("click", () => dialog.close());
    actions.append(cancel, replace);
    dialog.append(title, body, list, actions);
    dialog.addEventListener("close", () => { dialog.remove(); resolve(answer); }, { once: true });
    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
  });
}

function checkPartNamePresent(target = "bin") {
  if (target === "connector") return true;
  const val = ($("#part-name")?.value || "").trim();
  if (!val) {
    showBinNameRequiredDialog();
    return false;
  }
  return true;
}