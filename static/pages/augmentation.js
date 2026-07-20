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
let previewState = "not_generated";
let applying = false;
let applied = false;
let selectedPreset = "clear_day";
let augmentationJobs = [];
let augmentationJobsProjectId = null;
let augmentationJobsLoading = false;

const GROUP_BY_PRESET = {
  clear_day: "light",
  low_light: "light",
  rainy: "weather",
  foggy: "weather",
  motion_camera: "weather",
  strong_shadow: "light",
  wet_reflection: "weather",
  night_road: "light",
  suburban_mix: "weather",
  forest_road: "light",
  generalization: "weather"
};

const PRESET_META = {
  clear_day: { risk: "Low" },
  low_light: { risk: "Medium" },
  rainy: { risk: "Medium" },
  foggy: { risk: "Medium" },
  motion_camera: { risk: "Medium" },
  strong_shadow: { risk: "Medium" },
  wet_reflection: { risk: "Medium" },
  night_road: { risk: "High" },
  suburban_mix: { risk: "Low" },
  forest_road: { risk: "Medium" },
  generalization: { risk: "Low" }
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
  qsa("[data-aug-overlay]").forEach((button) => {
    button.addEventListener("click", () => button.classList.toggle("active"));
  });

  qs("#btn-preview-aug")?.addEventListener("click", triggerAugPreview);
  qs("#btn-reset-aug")?.addEventListener("click", resetAugmentationPolicy);
  qs("#btn-apply-aug")?.addEventListener("click", applyAugmentationToTrainSplit);
  qs("#btn-refresh-aug-jobs")?.addEventListener("click", () => loadAugmentationJobs(true));
  renderPresetDetails(selectedPreset);
  expandRelevantGroup(selectedPreset);
  highlightPresetSettings(selectedPreset);
  renderAugmentationJobHistory();
}

export function renderAugmentationPage(status) {
  updateSliderLabels();
  updateEstimatedCount();

  const stateInfo = getAugmentationState(status);
  augmentationUiState = stateInfo.state;
  if (!stateInfo.canPreview) previewState = "not_generated";

  renderReadinessGuard(stateInfo);
  renderPresetDetails(selectedPreset);
  highlightPresetSettings(selectedPreset);
  renderTargetScope(status);
  renderRiskCheck(stateInfo);
  renderPreviewOptions(status);
  updateControlState(stateInfo);
  loadAugmentationJobs(false);
  renderAugmentationJobHistory();
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
  const riskPassed = previewState === "ready";

  if (!status?.hasProject) {
    reasons.push(t("augmentation.reason.noProject"));
    return { state: "blocked_no_project", label: t("augmentation.state.blocked"), badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (!status.hasDataset) {
    reasons.push(t("augmentation.reason.noImages"));
    reasons.push(t("augmentation.reason.importImages"));
    return { state: "blocked_no_images", label: t("augmentation.state.blocked"), badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (!status.splitComplete || trainCount === 0) {
    reasons.push(t("augmentation.reason.noSplit"));
    reasons.push(t("augmentation.reason.createSplit"));
    return { state: "blocked_no_split", label: t("augmentation.state.blocked"), badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (previewCount === 0) {
    reasons.push(t("augmentation.reason.noPreview"));
    return { state: "blocked_no_preview_image", label: t("augmentation.state.blocked"), badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (applying) {
    return { state: "applying", label: t("augmentation.state.applying"), badge: "warning", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons: [t("augmentation.reason.running")] };
  }
  if (applied) {
    return { state: "applied", label: "Applied", badge: "success", canPreview: true, canApply: false, trainCount, valCount, testCount, previewCount, reasons: ["擴充已套用到 Train split，可前往 Training 開始新訓練。"] };
  }
  if (previewState === "ready") {
    return { state: "preview_ready", label: t("augmentation.state.previewReady"), badge: "success", canPreview: true, canApply: true, trainCount, valCount, testCount, previewCount, reasons: [t("augmentation.reason.previewDone")] };
  }
  if (previewState === "stale") {
    return { state: "preview_stale", label: "Preview stale", badge: "warning", canPreview: true, canApply: false, trainCount, valCount, testCount, previewCount, reasons: ["設定已變更，請重新產生預覽後再套用。"] };
  }
  if (previewState === "failed") {
    return { state: "preview_failed", label: "Preview failed", badge: "danger", canPreview: true, canApply: false, trainCount, valCount, testCount, previewCount, reasons: ["Preview 產生失敗，請調整設定後重試。"] };
  }
  return { state: "ready", label: t("augmentation.state.ready"), badge: "success", canPreview: true, canApply: riskPassed, trainCount, valCount, testCount, previewCount, reasons: [t("augmentation.reason.ready")] };
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
    case "preview_stale": return t("augmentation.message.previewStale");
    case "preview_failed": return t("augmentation.message.previewFailed");
    case "preview_ready": return t("augmentation.message.previewReady");
    case "applying": return t("augmentation.message.applying");
    case "applied": return t("augmentation.message.applied");
    default: return t("augmentation.message.default");
  }
}

function renderTargetScope(status) {
  const train = status?.splitCounts?.train || 0;
  const val = status?.splitCounts?.val || 0;
  const test = status?.splitCounts?.test || 0;
  const multiplier = Number(qs(MULTIPLIER)?.value || 1);
  const output = train * multiplier;

  setText("#aug-scope-train", String(train));
  setText("#aug-scope-val", `${val} excluded`);
  setText("#aug-scope-test", `${test} excluded`);
  setText("#aug-scope-output", `+${output}`);
  setText("#aug-final-count", `${train} → ${train + output}`);
  setText("#aug-info-train-count", `${train}`);
  setText("#aug-info-multiplier", `${multiplier}x`);
  setText("#aug-info-total-count", `+${output}`);
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

  const compact = (icon, text, stateClass = "is-warning") => {
    list.innerHTML = `
      <li class="${stateClass}">
        <i class="fa-solid ${icon}"></i>
        <span>${escapeHtml(text)}</span>
      </li>
    `;
  };

  if (!info.canPreview) {
    compact("fa-circle-exclamation", t("augmentation.risk.fixReadiness"), "is-warning");
  } else if (previewState === "stale") {
    compact("fa-rotate", t("augmentation.risk.previewStale"), "is-warning");
  } else if (previewState === "failed") {
    compact("fa-triangle-exclamation", t("augmentation.risk.previewFailed"), "is-warning");
  } else if (previewState !== "ready") {
    compact("fa-circle-info", t("augmentation.risk.previewMissing"), "is-info");
  } else {
    const checks = [
      { kind: "ok", text: t("augmentation.risk.train") },
      { kind: "ok", text: t("augmentation.risk.valTest") },
      { kind: "ok", text: t("augmentation.risk.originals") },
      { kind: "ok", text: t("augmentation.risk.previewOk") },
      { kind: "info", text: t("augmentation.risk.perspective") }
    ];

    list.innerHTML = checks.map((check) => `
      <li class="${check.kind === "ok" ? "is-ok" : "is-info"}">
        <i class="fa-solid ${check.kind === "ok" ? "fa-circle-check" : "fa-circle-info"}"></i>
        <span>${escapeHtml(check.text)}</span>
      </li>
    `).join("");
  }

  if (badge) {
    if (info.canApply) {
      badge.className = "summary-badge badge-success";
      badge.textContent = t("augmentation.risk.passed");
    } else if (info.canPreview) {
      badge.className = "summary-badge badge-warning";
      badge.textContent = previewState === "stale" ? t("augmentation.state.previewStale") : t("augmentation.risk.previewRequired");
    } else {
      badge.className = "summary-badge badge-danger";
      badge.textContent = t("augmentation.state.blocked");
    }
  }
}

function updateControlState(info) {
  const settingsDisabled = applying;
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
    previewBtn.disabled = applying;
    previewBtn.dataset.requires = !info.canPreview && !applying ? "custom" : "";
    previewBtn.dataset.blockReason = !info.canPreview && !applying ? info.reasons.join(" ") : "";
    previewBtn.setAttribute("aria-disabled", info.canPreview ? "false" : "true");
    previewBtn.innerHTML = info.state === "preview_generating"
      ? `<i class="fa-solid fa-spinner fa-spin"></i> ${escapeHtml(t("augmentation.previewRendering"))}`
      : `<i class="fa-solid fa-eye"></i> ${escapeHtml(t("augmentation.generatePreview"))}`;
  }

  const applyBtn = qs("#btn-apply-aug");
  if (applyBtn) {
    applyBtn.disabled = applying;
    applyBtn.dataset.requires = !info.canApply && !applying ? "custom" : "";
    applyBtn.dataset.blockReason = !info.canApply && !applying ? info.reasons.join(" ") : "";
    applyBtn.setAttribute("aria-disabled", info.canApply ? "false" : "true");
    applyBtn.innerHTML = applying
      ? `<i class="fa-solid fa-spinner fa-spin"></i> ${escapeHtml(t("augmentation.applyRunning"))}`
      : `<i class="fa-solid fa-wand-magic-sparkles"></i> ${escapeHtml(t("augmentation.applyTrain"))}`;
  }
}

function invalidatePreview() {
  if (previewState === "ready") previewState = "stale";
  else if (previewState !== "stale") previewState = "not_generated";
  applied = false;
  const img = qs("#aug-preview-img");
  const placeholder = qs("#aug-preview-placeholder");
  if (img) img.style.display = "none";
  if (placeholder) {
    placeholder.style.display = "block";
    placeholder.textContent = previewState === "stale" ? t("augmentation.message.previewStale") : t("augmentation.previewPlaceholder");
  }
  renderAugmentationPage(appState.currentProject ? getStatusFromProject() : { hasProject: false });
}

function validatePreviewSuccess() {
  previewState = "ready";
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
    placeholder.textContent = t("augmentation.previewPlaceholder");
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
      placeholder.textContent = "無法載入預覽圖片。";
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

  renderPresetDetails(presetName);
  expandRelevantGroup(presetName);
  highlightPresetSettings(presetName);

  updateSliderLabels();
  updateEstimatedCount();
  invalidatePreview();
}

function renderPresetDetails(presetName) {
  const meta = PRESET_META[presetName] || PRESET_META.clear_day;
  setText("#aug-preset-purpose", t(`augmentation.presetPurpose.${presetName}`));
  setText("#aug-preset-params", t(`augmentation.presetParams.${presetName}`));
  setText("#aug-preset-risk", meta.risk);
}

function expandRelevantGroup(presetName) {
  const targetGroup = GROUP_BY_PRESET[presetName] || "light";
  qsa("[data-aug-group]").forEach((group) => {
    group.open = group.dataset.augGroup === targetGroup;
  });
}

function highlightPresetSettings(presetName) {
  qsa("[data-aug-setting]").forEach((el) => el.classList.remove("is-related"));
  const related = {
    clear_day: ["brightness", "contrast"],
    low_light: ["brightness", "contrast", "shadow", "noise"],
    rainy: ["rain", "contrast", "motion"],
    foggy: ["fog", "contrast"],
    motion_camera: ["motion", "noise"],
    strong_shadow: ["shadow", "brightness", "contrast"],
    wet_reflection: ["rain", "brightness", "contrast"],
    night_road: ["brightness", "shadow", "noise"],
    suburban_mix: ["brightness", "contrast", "noise"],
    forest_road: ["shadow", "brightness", "contrast"],
    generalization: ["brightness", "contrast", "rain", "fog", "motion", "noise"]
  };
  (related[presetName] || []).forEach((name) => {
    qs(`[data-aug-setting="${name}"]`)?.classList.add("is-related");
  });
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
    previewState = "not_generated";
    applied = false;
    augmentationUiState = "preview_generating";
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 產生中...`;
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
    previewState = "failed";
    if (img) img.style.display = "none";
    if (placeholder) {
      placeholder.style.display = "block";
      placeholder.textContent = `Preview 產生失敗：${err.message}`;
    }
    eventBus.emit("toast", `Preview 產生失敗：${err.message}`);
    renderAugmentationPage(getStatusFromProject());
  } finally {
    if (btn) btn.innerHTML = `<i class="fa-solid fa-eye"></i> 產生預覽`;
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
    eventBus.emit("toast", data.message || "已套用到 Train Split。");
    eventBus.emit("refresh-project");
    await loadAugmentationJobs(true);
    applied = true;
    previewState = "not_generated";
  } catch (err) {
    eventBus.emit("toast", `套用失敗：${err.message}`);
  } finally {
    applying = false;
    renderAugmentationPage(getStatusFromProject());
  }
}

async function loadAugmentationJobs(force = false) {
  const projectId = appState.currentProjectId;
  if (!projectId) {
    augmentationJobs = [];
    augmentationJobsProjectId = null;
    renderAugmentationJobHistory();
    return;
  }
  if (!force && augmentationJobsProjectId === projectId) return;
  if (augmentationJobsLoading) return;

  augmentationJobsLoading = true;
  augmentationJobsProjectId = projectId;
  renderAugmentationJobHistory();
  try {
    const data = await apiFetch(`/api/projects/${projectId}/augmentation/jobs`);
    augmentationJobs = Array.isArray(data.jobs) ? data.jobs : [];
  } catch (err) {
    augmentationJobs = [];
    eventBus.emit("toast", `讀取擴充紀錄失敗：${err.message}`);
  } finally {
    augmentationJobsLoading = false;
    renderAugmentationJobHistory();
  }
}

function renderAugmentationJobHistory() {
  const list = qs("#aug-job-history-list");
  if (!list) return;

  if (!appState.currentProjectId) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(t("common.noProjectOpened"))}</div>`;
    return;
  }
  if (augmentationJobsLoading) {
    list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-spinner fa-spin"></i> ${escapeHtml(t("augmentation.job.loading"))}</div>`;
    return;
  }
  if (!augmentationJobs.length) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(t("augmentation.job.empty"))}</div>`;
    return;
  }

  list.innerHTML = augmentationJobs.slice(0, 6).map((job) => {
    const created = formatJobTime(job.created_at);
    const generated = Number(job.generated_count || 0);
    const sourceTrain = Number(job.source_train_count || 0);
    const multiplier = Number(job.multiplier || 1);
    const status = job.status || "completed";
    const statusKey = ["completed", "running", "failed"].includes(status)
      ? `augmentation.job.status.${status}`
      : "";
    const statusLabel = statusKey ? t(statusKey) : status;
    const risk = job.val_test_policy === "excluded"
      ? t("augmentation.job.valTestExcluded")
      : t("augmentation.job.checkPolicy");
    const params = Array.isArray(job.applied_parameters) && job.applied_parameters.length
      ? job.applied_parameters.join(", ")
      : t("augmentation.job.default");
    const outputPath = job.outputs?.images || "-";
    return `
      <article class="aug-job-card">
        <div class="aug-job-main">
          <div>
            <strong>${escapeHtml(job.job_id || "augmentation_job")}</strong>
            <span>${escapeHtml(created)}</span>
          </div>
          <span class="summary-badge ${status === "completed" ? "badge-success" : "badge-warning"}">${escapeHtml(statusLabel)}</span>
        </div>
        <div class="aug-job-stats">
          <span><b>+${generated}</b><small>${escapeHtml(t("augmentation.job.generated"))}</small></span>
          <span><b>${sourceTrain}</b><small>${escapeHtml(t("augmentation.job.trainSource"))}</small></span>
          <span><b>${multiplier}x</b><small>${escapeHtml(t("augmentation.job.multiplier"))}</small></span>
        </div>
        <dl class="aug-job-meta">
          <div><dt>${escapeHtml(t("augmentation.job.policy"))}</dt><dd>${escapeHtml(risk)}</dd></div>
          <div><dt>${escapeHtml(t("augmentation.job.parameters"))}</dt><dd>${escapeHtml(params)}</dd></div>
          <div><dt>${escapeHtml(t("augmentation.job.output"))}</dt><dd title="${escapeHtml(outputPath)}">${escapeHtml(outputPath)}</dd></div>
        </dl>
      </article>
    `;
  }).join("");
}

function formatJobTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(appState.language === "en" ? "en-US" : "zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
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
