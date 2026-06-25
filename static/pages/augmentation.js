import { eventBus } from "../event_bus.js";
import { appState, augmentationPresets, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, escapeHtml } from "../utils.js";

const SLIDERS = [
  "#aug-light-brightness",
  "#aug-light-contrast",
  "#aug-weather-rain",
  "#aug-weather-fog",
  "#aug-motion-blur",
  "#aug-camera-noise"
];

const SHADOW = "#aug-light-shadow";
const MULTIPLIER = "#aug-multiplier";
const PREVIEW_SELECT = "#aug-preview-select-img";

let augmentationUiState = "blocked_no_project";
let previewReady = false;
let applying = false;
let selectedPreset = "clear_day";

const PRESET_DETAILS = {
  clear_day: "augmentation.preset.clearDayDetail",
  low_light: "augmentation.preset.lowLightHelp",
  rainy: "augmentation.preset.rainyHelp",
  foggy: "augmentation.preset.foggyHelp",
  motion_camera: "augmentation.preset.motionHelp"
};

export function initAugmentation() {
  eventBus.on("language-changed", () => renderAugmentationPage(getStatusFromProject()));
  SLIDERS.forEach((selector) => {
    const el = qs(selector);
    if (!el) return;
    el.addEventListener("input", () => {
      updateSliderLabels();
      invalidatePreview();
    });
    el.addEventListener("change", invalidatePreview);
  });

  qs(SHADOW)?.addEventListener("change", invalidatePreview);

  const multEl = qs(MULTIPLIER);
  if (multEl) {
    multEl.addEventListener("input", () => {
      updateEstimatedCount();
      invalidatePreview();
    });
    multEl.addEventListener("change", () => {
      updateEstimatedCount();
      invalidatePreview();
    });
  }

  qs(PREVIEW_SELECT)?.addEventListener("change", () => {
    invalidatePreview();
    const filename = qs(PREVIEW_SELECT)?.value;
    if (filename) drawBeforeCanvas(filename);
    else resetPreviewUI();
  });

  qsa("[data-aug-preset]").forEach((button) => {
    button.addEventListener("click", () => applyAugmentationPreset(button.dataset.augPreset));
  });

  qs("#btn-preview-aug")?.addEventListener("click", triggerAugPreview);
  qs("#btn-reset-aug")?.addEventListener("click", resetAugmentationPolicy);
  qs("#btn-apply-aug")?.addEventListener("click", applyAugmentationToTrainSplit);
}

export function renderAugmentationPage(status) {
  updateSliderLabels();
  updateEstimatedCount();

  const stateInfo = getAugmentationState(status);
  augmentationUiState = stateInfo.state;
  if (!stateInfo.canPreview) previewReady = false;

  renderReadinessGuard(stateInfo);
  renderTargetScope(status);
  renderRiskCheck(stateInfo);
  renderPreviewOptions(status);
  updateControlState(stateInfo);
}

function getRawImages() {
  return (appState.currentProject?.images || []).filter((img) => !img.is_augmented);
}

function getTrainImages() {
  return getRawImages().filter((img) => img.split === "train");
}

function getPreviewImages() {
  return getTrainImages().filter((img) => img.status === "annotated");
}

function getAugmentationState(status) {
  const trainCount = status?.splitCounts?.train || 0;
  const valCount = status?.splitCounts?.val || 0;
  const testCount = status?.splitCounts?.test || 0;
  const previewCount = getPreviewImages().length;
  const reasons = [];

  if (!status?.hasProject) {
    reasons.push("No project is open.");
    return { state: "blocked_no_project", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (!status.hasDataset) {
    reasons.push("No images imported.");
    reasons.push("Import images in Dataset before configuring augmentation.");
    return { state: "blocked_no_images", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (!status.splitComplete || trainCount === 0) {
    reasons.push("Train / Val / Test split has not been created.");
    reasons.push("Create a split so augmentation can target Train only.");
    return { state: "blocked_no_split", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (previewCount === 0) {
    reasons.push("No annotated train image is available for preview.");
    return { state: "blocked_no_preview_image", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (applying) {
    return { state: "applying", label: t("augmentation.state.applying"), badge: "warning", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons: [t("augmentation.reason.running")] };
  }
  if (previewReady) {
    return { state: "preview_ready", label: t("augmentation.state.previewReady"), badge: "success", canPreview: true, canApply: true, trainCount, valCount, testCount, previewCount, reasons: [t("augmentation.reason.previewDone")] };
  }
  return { state: "ready", label: t("augmentation.state.ready"), badge: "success", canPreview: true, canApply: false, trainCount, valCount, testCount, previewCount, reasons: [t("augmentation.reason.ready")] };
}

function renderReadinessGuard(info) {
  const badge = qs("#aug-readiness-badge");
  const message = qs("#aug-readiness-message");
  const reasons = qs("#aug-readiness-reasons");
  const card = qs("#aug-readiness-card");

  if (badge) {
    badge.className = `summary-badge badge-${info.badge}`;
    badge.textContent = info.label;
  }
  if (message) {
    message.textContent = getReadinessMessage(info);
  }
  if (reasons) {
    reasons.innerHTML = info.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
  }
  if (card) {
    card.dataset.state = info.state;
  }
}

function getReadinessMessage(info) {
  switch (info.state) {
    case "blocked_no_project": return t("augmentation.message.noProject");
    case "blocked_no_images": return t("augmentation.message.noImages");
    case "blocked_no_split": return t("augmentation.message.noSplit");
    case "blocked_no_preview_image": return t("augmentation.message.noPreviewImage");
    case "ready": return t("augmentation.message.ready", { count: info.trainCount });
    case "preview_ready": return t("augmentation.message.previewReady");
    case "applying": return t("augmentation.message.applying");
    default: return t("augmentation.subtitle");
  }
}

function renderTargetScope(status) {
  const train = status?.splitCounts?.train || 0;
  const val = status?.splitCounts?.val || 0;
  const test = status?.splitCounts?.test || 0;
  const multiplier = Number(qs(MULTIPLIER)?.value || 1);
  const output = train * multiplier;

  setText("#aug-scope-train", String(train));
  setText("#aug-scope-val", t("augmentation.excluded", { count: val }));
  setText("#aug-scope-test", t("augmentation.excluded", { count: test }));
  setText("#aug-scope-output", `${train} -> ${train + output}`);
  setText("#aug-info-train-count", `${train}`);
  setText("#aug-info-multiplier", `${multiplier}x`);
  setText("#aug-info-total-count", `${output}`);
}

function renderPreviewOptions(status) {
  const select = qs(PREVIEW_SELECT);
  if (!select) return;

  const options = getPreviewImages().map((img) => `<option value="${escapeHtml(img.filename)}">${escapeHtml(img.filename)}</option>`);
  select.innerHTML = options.length ? options.join("") : `<option value="">${escapeHtml(t("augmentation.noPreviewOption"))}</option>`;
  select.disabled = !status?.splitComplete || options.length === 0;

  if (select.value) drawBeforeCanvas(select.value);
  else resetPreviewUI();
}

function renderRiskCheck(info) {
  const list = qs("#aug-risk-list");
  const badge = qs("#aug-risk-badge");
  if (!list) return;

  const checks = [
    { ok: info.trainCount > 0, text: t("augmentation.risk.train") },
    { ok: true, text: t("augmentation.risk.valTest") },
    { ok: true, text: t("augmentation.risk.originals") },
    { ok: qs("#aug-camera-perspective")?.disabled === true, text: t("augmentation.risk.perspective") },
    { ok: previewReady, text: previewReady ? t("augmentation.risk.previewOk") : t("augmentation.risk.previewMissing") }
  ];

  list.innerHTML = checks.map((check) => `
    <li class="${check.ok ? "is-ok" : "is-warning"}">
      <i class="fa-solid ${check.ok ? "fa-circle-check" : "fa-triangle-exclamation"}"></i>
      <span>${escapeHtml(check.text)}</span>
    </li>
  `).join("");

  if (badge) {
    if (info.canApply) {
      badge.className = "summary-badge badge-success";
      badge.textContent = t("augmentation.risk.passed");
    } else if (info.canPreview) {
      badge.className = "summary-badge badge-warning";
      badge.textContent = t("augmentation.risk.previewRequired");
    } else {
      badge.className = "summary-badge badge-danger";
      badge.textContent = t("augmentation.state.blocked");
    }
  }
}

function updateControlState(info) {
  const settingsDisabled = info.state.startsWith("blocked_") || applying;
  qsa("#aug-settings-panel input, #aug-settings-panel button").forEach((el) => {
    if (el.id === "aug-camera-perspective") {
      el.disabled = true;
      return;
    }
    el.disabled = settingsDisabled;
  });
  qsa("[data-aug-preset]").forEach((button) => {
    button.disabled = settingsDisabled;
  });

  const previewBtn = qs("#btn-preview-aug");
  if (previewBtn) {
    previewBtn.disabled = !info.canPreview || applying;
    previewBtn.innerHTML = info.state === "preview_generating"
      ? `<i class="fa-solid fa-spinner fa-spin"></i> Rendering...`
      : `<i class="fa-solid fa-eye"></i> Generate Preview`;
  }

  const applyBtn = qs("#btn-apply-aug");
  if (applyBtn) {
    applyBtn.disabled = !info.canApply || applying;
    applyBtn.innerHTML = applying
      ? `<i class="fa-solid fa-spinner fa-spin"></i> Applying...`
      : `<i class="fa-solid fa-wand-magic-sparkles"></i> Apply to Train Split`;
  }
}

function invalidatePreview() {
  previewReady = false;
  const img = qs("#aug-preview-img");
  const placeholder = qs("#aug-preview-placeholder");
  if (img) img.style.display = "none";
  if (placeholder) {
    placeholder.style.display = "block";
    placeholder.textContent = t("augmentation.previewPlaceholder");
  }
  renderAugmentationPage(appState.currentProject ? getStatusFromProject() : { hasProject: false });
}

function validatePreviewSuccess() {
  previewReady = true;
  renderAugmentationPage(getStatusFromProject());
}

function resetPreviewUI() {
  const beforeCanvas = qs("#aug-before-canvas");
  const beforePlaceholder = qs("#aug-before-placeholder");
  const img = qs("#aug-preview-img");
  const placeholder = qs("#aug-preview-placeholder");

  if (beforeCanvas) beforeCanvas.style.display = "none";
  if (beforePlaceholder) {
    beforePlaceholder.style.display = "block";
    beforePlaceholder.textContent = t("augmentation.beforePlaceholder");
  }
  if (img) img.style.display = "none";
  if (placeholder) {
    placeholder.style.display = "block";
    placeholder.textContent = "Generate Preview to inspect the result.";
  }
}

function drawBeforeCanvas(filename) {
  const canvas = qs("#aug-before-canvas");
  const placeholder = qs("#aug-before-placeholder");
  if (!canvas || !appState.currentProject || !filename) return;

  const imgMetadata = getPreviewImages().find((img) => img.filename === filename);
  if (!imgMetadata) {
    resetPreviewUI();
    return;
  }

  if (placeholder) placeholder.style.display = "none";
  canvas.style.display = "block";

  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.onload = () => {
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);
    drawAnnotations(ctx, img, imgMetadata.annotations || []);
  };
  img.onerror = () => {
    canvas.style.display = "none";
    if (placeholder) {
      placeholder.style.display = "block";
      placeholder.textContent = t("augmentation.loadPreviewFailed");
    }
  };
  img.src = `/api/projects/${appState.currentProjectId}/images/${encodeURIComponent(filename)}`;
}

function drawAnnotations(ctx, img, annotations) {
  annotations.forEach((ann) => {
    ctx.strokeStyle = "#10B981";
    ctx.lineWidth = Math.max(3, Math.round(img.width / 250));
    ctx.fillStyle = "rgba(16, 185, 129, 0.15)";

    let pts = [];
    const type = ann.type || (ann.points ? "polygon" : "bbox");
    if (type === "polygon" && ann.points && ann.points.length > 0) {
      if (Array.isArray(ann.points[0])) pts = ann.points;
      else if (typeof ann.points[0] === "number") {
        for (let i = 0; i < ann.points.length; i += 2) pts.push([ann.points[i], ann.points[i + 1]]);
      }
    }

    if (pts.length >= 3) {
      drawPolygon(ctx, pts, ann.category || ann.label || "label", img.width);
    } else if (ann.bbox && ann.bbox.length === 4) {
      drawBbox(ctx, ann.bbox, ann.category || ann.label || "label", img);
    }
  });
}

function drawPolygon(ctx, pts, label, width) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  pts.slice(1).forEach((p) => ctx.lineTo(p[0], p[1]));
  ctx.closePath();
  ctx.stroke();
  ctx.fill();
  drawLabel(ctx, label, pts[0][0], pts[0][1], width);
}

function drawBbox(ctx, bbox, label, img) {
  const [xc, yc, w, h] = bbox;
  const x1 = (xc - w / 2) * img.width;
  const y1 = (yc - h / 2) * img.height;
  const bw = w * img.width;
  const bh = h * img.height;
  ctx.beginPath();
  ctx.rect(x1, y1, bw, bh);
  ctx.stroke();
  ctx.fill();
  drawLabel(ctx, label, x1, y1, img.width);
}

function drawLabel(ctx, label, x, y, width) {
  const fontSize = Math.max(12, Math.round(width / 45));
  ctx.font = `bold ${fontSize}px sans-serif`;
  const labelWidth = ctx.measureText(label).width;
  ctx.fillStyle = "#10B981";
  ctx.fillRect(x, Math.max(0, y - fontSize - 6), labelWidth + 10, fontSize + 6);
  ctx.fillStyle = "#ffffff";
  ctx.fillText(label, x + 5, Math.max(fontSize, y - 4));
  ctx.fillStyle = "rgba(16, 185, 129, 0.15)";
}

function applyAugmentationPreset(presetName) {
  const preset = augmentationPresets[presetName];
  if (!preset) return;
  selectedPreset = presetName;

  setValue("#aug-light-brightness", preset.brightness);
  setValue("#aug-light-contrast", preset.contrast);
  setChecked("#aug-light-shadow", preset.shadow);
  setValue("#aug-weather-rain", preset.rain);
  setValue("#aug-weather-fog", preset.fog);
  setValue("#aug-motion-blur", preset.motionBlur);
  setValue("#aug-camera-noise", preset.noise);
  setValue("#aug-camera-perspective", 0);

  qsa("[data-aug-preset]").forEach((button) => {
    button.classList.toggle("active", button.dataset.augPreset === presetName);
  });

  const detail = qs("#aug-preset-detail p");
  if (detail) detail.textContent = t(PRESET_DETAILS[presetName] || "augmentation.preset.clearDayDetail");

  updateSliderLabels();
  updateEstimatedCount();
  invalidatePreview();
}

function resetAugmentationPolicy() {
  applyAugmentationPreset("clear_day");
  setValue(MULTIPLIER, 1);
  invalidatePreview();
}

function getAugmentationConfig() {
  return {
    light: {
      brightness: Number(qs("#aug-light-brightness")?.value || 0),
      contrast: Number(qs("#aug-light-contrast")?.value || 0),
      shadow: Boolean(qs("#aug-light-shadow")?.checked)
    },
    weather: {
      rain: Number(qs("#aug-weather-rain")?.value || 0),
      fog: Number(qs("#aug-weather-fog")?.value || 0)
    },
    motion: {
      motion_blur: Number(qs("#aug-motion-blur")?.value || 0)
    },
    camera: {
      noise: Number(qs("#aug-camera-noise")?.value || 0),
      perspective: 0
    },
    preset: selectedPreset
  };
}

async function triggerAugPreview() {
  const status = getStatusFromProject();
  const info = getAugmentationState(status);
  const filename = qs(PREVIEW_SELECT)?.value;
  if (!info.canPreview || !appState.currentProjectId || !filename) return;

  const btn = qs("#btn-preview-aug");
  const img = qs("#aug-preview-img");
  const placeholder = qs("#aug-preview-placeholder");

  try {
    previewReady = false;
    augmentationUiState = "preview_generating";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${escapeHtml(t("augmentation.previewRendering"))}`;
    }

    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/augment-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, config: getAugmentationConfig() })
    });

    if (img) {
      img.src = data.preview;
      img.style.display = "block";
    }
    if (placeholder) placeholder.style.display = "none";
    validatePreviewSuccess();
  } catch (err) {
    previewReady = false;
    if (img) img.style.display = "none";
    if (placeholder) {
      placeholder.style.display = "block";
      placeholder.textContent = t("augmentation.previewFailed", { message: err.message });
    }
    eventBus.emit("toast", t("augmentation.previewFailed", { message: err.message }));
    renderAugmentationPage(getStatusFromProject());
  } finally {
    if (btn) btn.innerHTML = `<i class="fa-solid fa-eye"></i> ${escapeHtml(t("augmentation.generatePreview"))}`;
  }
}

async function applyAugmentationToTrainSplit() {
  const info = getAugmentationState(getStatusFromProject());
  if (!info.canApply || !appState.currentProjectId) return;

  applying = true;
  renderAugmentationPage(getStatusFromProject());

  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/apply-augmentation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_split: "train",
        multiplier: Number(qs(MULTIPLIER)?.value || 1),
        config: getAugmentationConfig()
      })
    });
    eventBus.emit("toast", data.message || t("augmentation.applyDone"));
    eventBus.emit("refresh-project");
    previewReady = false;
  } catch (err) {
    eventBus.emit("toast", t("augmentation.applyFailed", { message: err.message }));
  } finally {
    applying = false;
    renderAugmentationPage(getStatusFromProject());
  }
}

function updateSliderLabels() {
  const map = {
    "#aug-light-brightness": "#val-brightness",
    "#aug-light-contrast": "#val-contrast",
    "#aug-weather-rain": "#val-rain",
    "#aug-weather-fog": "#val-fog",
    "#aug-motion-blur": "#val-motion-blur",
    "#aug-camera-noise": "#val-camera-noise",
    "#aug-camera-perspective": "#val-camera-perspective"
  };
  Object.entries(map).forEach(([inputSelector, labelSelector]) => {
    const input = qs(inputSelector);
    const label = qs(labelSelector);
    if (input && label) label.textContent = Number(input.value || 0).toFixed(2);
  });
}

function updateEstimatedCount() {
  renderTargetScope(getStatusFromProject());
}

function getStatusFromProject() {
  const project = appState.currentProject;
  const rawImages = getRawImages();
  const splitCounts = rawImages.reduce((acc, img) => {
    if (img.split) acc[img.split] = (acc[img.split] || 0) + 1;
    return acc;
  }, { train: 0, val: 0, test: 0 });
  return {
    hasProject: Boolean(project),
    hasDataset: rawImages.length > 0,
    splitCounts,
    splitComplete: splitCounts.train > 0 && splitCounts.val > 0
  };
}

function setText(selector, value) {
  const el = qs(selector);
  if (el) el.textContent = value;
}

function setValue(selector, value) {
  const el = qs(selector);
  if (el) el.value = value;
}

function setChecked(selector, value) {
  const el = qs(selector);
  if (el) el.checked = Boolean(value);
}
