import { eventBus } from "../event_bus.js";
import { appState, augmentationPresets } from "../state.js";
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
  clear_day: {
    purpose: "建立低風險晴天基準，微調亮度與對比。",
    params: "亮度、對比",
    risk: "Low"
  },
  low_light: {
    purpose: "模擬低照度、陰影與曝光不足場景。",
    params: "亮度、對比、陰影、雜訊",
    risk: "Medium"
  },
  rainy: {
    purpose: "模擬雨天與濕潤表面造成的視覺變化。",
    params: "雨天、對比、運動模糊",
    risk: "Medium"
  },
  foggy: {
    purpose: "降低能見度並模擬霧氣或霧霾。",
    params: "霧氣、對比",
    risk: "Medium"
  },
  motion_camera: {
    purpose: "模擬移動鏡頭、車載影像與相機雜訊。",
    params: "運動模糊、相機雜訊",
    risk: "Medium"
  },
  strong_shadow: {
    purpose: "強化樹影、建築陰影與局部暗部變化。",
    params: "陰影、亮度、對比",
    risk: "Medium"
  },
  wet_reflection: {
    purpose: "模擬濕地反光與鏡面反射造成的辨識干擾。",
    params: "雨天、亮度、對比",
    risk: "Medium"
  },
  night_road: {
    purpose: "模擬夜間道路、低光源與高雜訊影像。",
    params: "亮度、陰影、相機雜訊",
    risk: "High"
  },
  suburban_mix: {
    purpose: "混合郊區常見的光照、路面與相機差異。",
    params: "亮度、對比、雜訊",
    risk: "Low"
  },
  forest_road: {
    purpose: "模擬樹蔭、斑駁光影與森林道路場景。",
    params: "陰影、亮度、對比",
    risk: "Medium"
  },
  generalization: {
    purpose: "平衡各種環境變化，強化整體泛化能力。",
    params: "亮度、對比、雨天、霧氣、運動模糊、雜訊",
    risk: "Low"
  }
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
  applyAugmentationStaticCopy();
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
    reasons.push("尚未開啟專案。");
    return { state: "blocked_no_project", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (!status.hasDataset) {
    reasons.push("尚未匯入圖片資料。");
    reasons.push("請先前往 Dataset 匯入圖片。");
    return { state: "blocked_no_images", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (!status.splitComplete || trainCount === 0) {
    reasons.push("尚未建立 Train / Val / Test split。");
    reasons.push("請先建立 Split，讓擴充只套用到 Train split。");
    return { state: "blocked_no_split", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (previewCount === 0) {
    reasons.push("Train split 中沒有可預覽的已標註圖片。");
    return { state: "blocked_no_preview_image", label: "Blocked", badge: "danger", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons };
  }
  if (applying) {
    return { state: "applying", label: "Applying", badge: "warning", canPreview: false, canApply: false, trainCount, valCount, testCount, previewCount, reasons: ["擴充作業執行中。"] };
  }
  if (applied) {
    return { state: "applied", label: "Applied", badge: "success", canPreview: true, canApply: false, trainCount, valCount, testCount, previewCount, reasons: ["擴充已套用到 Train split，可前往 Training 開始新訓練。"] };
  }
  if (previewState === "ready") {
    return { state: "preview_ready", label: "Preview Ready", badge: "success", canPreview: true, canApply: true, trainCount, valCount, testCount, previewCount, reasons: ["Preview 已產生，Risk Check 已通過。"] };
  }
  if (previewState === "stale") {
    return { state: "preview_stale", label: "Preview stale", badge: "warning", canPreview: true, canApply: false, trainCount, valCount, testCount, previewCount, reasons: ["設定已變更，請重新產生預覽後再套用。"] };
  }
  if (previewState === "failed") {
    return { state: "preview_failed", label: "Preview failed", badge: "danger", canPreview: true, canApply: false, trainCount, valCount, testCount, previewCount, reasons: ["Preview 產生失敗，請調整設定後重試。"] };
  }
  return { state: "ready", label: "Ready", badge: "success", canPreview: true, canApply: riskPassed, trainCount, valCount, testCount, previewCount, reasons: ["Train 圖片可用，請先產生 Preview。"] };
}

function applyAugmentationStaticCopy() {
  setText("#page-augmentation .page-header h1", "物理擴充控制台");
  setText("#page-augmentation .page-header p", "透過物理擴充提升資料多樣性，並只套用到 Train split。");
  setText("#aug-readiness-card h2", "擴充就緒狀態");
  setText("#aug-go-dataset span", "前往 Dataset");
  setText("#aug-go-split span", "建立 Split");
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
    case "blocked_no_project": return "請先建立或開啟專案。";
    case "blocked_no_images": return "尚未匯入圖片，無法進行物理擴充。";
    case "blocked_no_split": return "尚未建立 Train / Val / Test split，無法安全套用擴充。";
    case "blocked_no_preview_image": return "Train split 中沒有可預覽的已標註圖片。";
    case "ready": return "Train split 可用，Val/Test 已排除，已可產生預覽。";
    case "preview_stale": return "設定已變更，請重新產生預覽。";
    case "preview_failed": return "Preview 產生失敗，請調整設定後重試。";
    case "preview_ready": return "Preview 已完成，可套用到 Train Split。";
    case "applying": return "正在套用到 Train Split，請稍候。";
    case "applied": return "擴充已套用到 Train Split。";
    default: return "物理擴充只會套用到 Train split，Val/Test 會保持排除。";
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
  select.innerHTML = options.length ? options.join("") : `<option value="">沒有可預覽的已標註 Train 圖片</option>`;
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
    compact("fa-circle-exclamation", "請先修正上方就緒狀態問題。", "is-warning");
  } else if (previewState === "stale") {
    compact("fa-rotate", "設定已變更，請重新產生 Preview。", "is-warning");
  } else if (previewState === "failed") {
    compact("fa-triangle-exclamation", "Preview 產生失敗，請調整設定後重試。", "is-warning");
  } else if (previewState !== "ready") {
    compact("fa-circle-info", "Preview required：產生預覽後才能套用到 Train Split。", "is-info");
  } else {
    const checks = [
      { kind: "ok", text: "Train split 有目標圖片。" },
      { kind: "ok", text: "Val/Test 已排除，避免評估資料洩漏。" },
      { kind: "ok", text: "原圖會保留，系統僅產生擴充副本。" },
      { kind: "ok", text: "Preview 已成功產生。" },
      { kind: "info", text: "Perspective 已停用，直到 polygon / bbox 重映射完成驗證。" }
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
      badge.textContent = "Passed";
    } else if (info.canPreview) {
      badge.className = "summary-badge badge-warning";
      badge.textContent = previewState === "stale" ? "Preview stale" : "Preview required";
    } else {
      badge.className = "summary-badge badge-danger";
      badge.textContent = "Blocked";
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
      ? `<i class="fa-solid fa-spinner fa-spin"></i> 產生中...`
      : `<i class="fa-solid fa-eye"></i> 產生預覽`;
  }

  const applyBtn = qs("#btn-apply-aug");
  if (applyBtn) {
    applyBtn.disabled = !info.canApply || applying;
    applyBtn.innerHTML = applying
      ? `<i class="fa-solid fa-spinner fa-spin"></i> 套用中...`
      : `<i class="fa-solid fa-wand-magic-sparkles"></i> 套用到 Train Split`;
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
    placeholder.textContent = previewState === "stale" ? "設定已變更，請重新產生 Preview。" : "產生 Preview 後檢查結果。";
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
    beforePlaceholder.textContent = "請選擇已標註的 Train 圖片。";
  }
  if (img) img.style.display = "none";
  if (placeholder) {
    placeholder.style.display = "block";
    placeholder.textContent = "產生 Preview 後檢查結果。";
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
  setText("#aug-preset-purpose", meta.purpose);
  setText("#aug-preset-params", meta.params);
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
    list.innerHTML = `<div class="empty-state">尚未開啟專案。</div>`;
    return;
  }
  if (augmentationJobsLoading) {
    list.innerHTML = `<div class="empty-state"><i class="fa-solid fa-spinner fa-spin"></i> 正在讀取擴充紀錄...</div>`;
    return;
  }
  if (!augmentationJobs.length) {
    list.innerHTML = `<div class="empty-state">尚無擴充紀錄。套用到 Train Split 後會顯示在這裡。</div>`;
    return;
  }

  list.innerHTML = augmentationJobs.slice(0, 6).map((job) => {
    const created = formatJobTime(job.created_at);
    const generated = Number(job.generated_count || 0);
    const sourceTrain = Number(job.source_train_count || 0);
    const multiplier = Number(job.multiplier || 1);
    const status = job.status || "completed";
    const risk = job.val_test_policy === "excluded" ? "Val/Test excluded" : "Check output policy";
    const params = Array.isArray(job.applied_parameters) && job.applied_parameters.length
      ? job.applied_parameters.join(", ")
      : "default";
    const outputPath = job.outputs?.images || "-";
    return `
      <article class="aug-job-card">
        <div class="aug-job-main">
          <div>
            <strong>${escapeHtml(job.job_id || "augmentation_job")}</strong>
            <span>${escapeHtml(created)}</span>
          </div>
          <span class="summary-badge ${status === "completed" ? "badge-success" : "badge-warning"}">${escapeHtml(status)}</span>
        </div>
        <div class="aug-job-stats">
          <span><b>+${generated}</b><small>generated</small></span>
          <span><b>${sourceTrain}</b><small>train source</small></span>
          <span><b>${multiplier}x</b><small>multiplier</small></span>
        </div>
        <dl class="aug-job-meta">
          <div><dt>Policy</dt><dd>${escapeHtml(risk)}</dd></div>
          <div><dt>Params</dt><dd>${escapeHtml(params)}</dd></div>
          <div><dt>Output</dt><dd title="${escapeHtml(outputPath)}">${escapeHtml(outputPath)}</dd></div>
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
