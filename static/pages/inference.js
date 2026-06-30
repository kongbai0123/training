import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setHTML, escapeHtml, copyText } from "../utils.js";

let loadedProjectId = null;
let selectedFileUrl = "";
let modelsLoading = false;

export function initInference() {
  qs("#btn-refresh-models")?.addEventListener("click", () => loadInferenceModels(true));
  qs("#btn-run-inference")?.addEventListener("click", runInference);
  qs("#inference-image-file")?.addEventListener("change", handleImageFileChange);
  qs("#inference-image-path")?.addEventListener("input", (e) => {
    if (e.target.value.trim()) {
      appState.inferenceLastBatchResults = null;
      const fileInput = qs("#inference-image-file");
      if (fileInput) fileInput.value = "";
      if (selectedFileUrl) {
        URL.revokeObjectURL(selectedFileUrl);
        selectedFileUrl = "";
      }
      const img = qs("#inference-original-img");
      const placeholder = qs("#inference-original-placeholder");
      if (img) {
        img.src = "";
        img.style.display = "none";
      }
      if (placeholder) placeholder.style.display = "block";
    }
    updateRunButtonState();
  });

  [
    "#inference-conf",
    "#inference-iou",
    "#inference-imgsz",
    "#inference-device",
    "#inference-mask-opacity",
    "#inference-show-mask",
    "#inference-show-bbox",
    "#inference-class-filter"
  ].forEach((selector) => {
    qs(selector)?.addEventListener("input", updateRunButtonState);
    qs(selector)?.addEventListener("change", updateRunButtonState);
  });

  qs("#btn-copy-inference-path")?.addEventListener("click", () => {
    const path = appState.inferenceLastResult?.paths?.job_dir;
    if (path) copyText(path);
  });

  qs("#btn-view-inference-output")?.addEventListener("click", () => {
    const url = appState.inferenceLastResult?.urls?.annotated_image;
    if (url) window.open(url, "_blank", "noopener");
  });
}

export function renderInferencePage(status) {
  if (!qs("#page-inference")) return;

  if (status.hasProject && loadedProjectId !== appState.currentProjectId && !modelsLoading) {
    loadInferenceModels(false);
  }

  // 根據 Local Trusted Mode 動態管理本機路徑輸入框
  const pathInput = qs("#inference-image-path");
  if (pathInput) {
    const trusted = appState.systemHealth?.local_trusted_mode === true;
    pathInput.disabled = !trusted;
    if (!trusted) {
      pathInput.placeholder = "本機路徑推論已停用 (Trusted Local Mode 關閉)";
      pathInput.value = "";
    } else {
      pathInput.placeholder = "輸入本機圖片絕對路徑，可用分號分隔多張圖 (e.g. C:\\path\\to\\image_1.jpg; C:\\path\\to\\image_2.jpg)";
    }
  }

  renderModelList(status);
  renderInferenceResult();
  updateRunButtonState();
}

async function loadInferenceModels(force) {
  if (!appState.currentProjectId) {
    appState.models = [];
    loadedProjectId = null;
    appState.inferenceSelectedModelId = "";
    renderModelList();
    updateRunButtonState();
    return;
  }
  if (!force && loadedProjectId === appState.currentProjectId && (appState.models || []).length > 0) return;

  modelsLoading = true;
  setInferenceError("");
  renderModelList();
  updateRunButtonState();

  try {
    const models = await apiFetch(`/api/projects/${appState.currentProjectId}/models`);
    appState.models = Array.isArray(models) ? models : [];
    loadedProjectId = appState.currentProjectId;
    ensureSelectedModel();
  } catch (err) {
    appState.models = [];
    appState.inferenceSelectedModelId = "";
    setInferenceError(`Model Registry 載入失敗：${err.message}`);
  } finally {
    modelsLoading = false;
    renderModelList();
    updateRunButtonState();
  }
}

function renderModelList(status = null) {
  const container = qs("#inference-model-list");
  if (!container) return;

  if (!appState.currentProjectId) {
    setHTML("#inference-model-list", `<div class="empty-state">請先載入專案。</div>`);
    return;
  }

  if (modelsLoading) {
    setHTML("#inference-model-list", `<div class="empty-state">正在掃描可用模型權重...</div>`);
    return;
  }

  const models = appState.models || [];
  ensureSelectedModel();

  if (!models.length) {
    setHTML("#inference-model-list", `
      <div class="empty-state">
        <strong>No trained weights found.</strong>
        <p>請先到 Training 完成一次訓練，或確認 best.pt / last.pt 是否存在於 training/runs/*/weights。</p>
      </div>
    `);
    return;
  }

  const projectTask = status?.taskType || appState.currentProject?.task_type || "";
  setHTML("#inference-model-list", models.map((model) => {
    const selected = model.model_id === appState.inferenceSelectedModelId ? "selected" : "";
    const compatible = isModelCompatible(projectTask, model.task_type);
    return `
      <button type="button" class="model-registry-item ${selected}" data-model-id="${escapeHtml(model.model_id)}">
        <div class="model-registry-main">
          <strong>${escapeHtml(model.run_id)} / ${escapeHtml(model.weight_type)}.pt</strong>
          <span>${escapeHtml(model.task_type)} · ${escapeHtml(formatDate(model.created_at))}</span>
        </div>
        <div class="model-registry-metrics">
          <span>mAP50(M): ${formatMetric(model.best_map50_m)}</span>
          <span>mAP50-95(M): ${formatMetric(model.best_map50_95_m)}</span>
          <span>${formatBytes(model.file_size)}</span>
          <span class="status-badge ${compatible ? "success" : "warning"}">${compatible ? "Ready" : "Task mismatch"}</span>
        </div>
      </button>
    `;
  }).join(""));

  qsa("[data-model-id]").forEach((button) => {
    button.addEventListener("click", () => {
      appState.inferenceSelectedModelId = button.dataset.modelId;
      renderModelList(status);
      updateRunButtonState();
    });
  });
}

function handleImageFileChange(event) {
  const files = [...(event.target.files || [])];
  const file = files[0];
  appState.inferenceLastBatchResults = null;
  if (files.length) {
    const pathInput = qs("#inference-image-path");
    if (pathInput) pathInput.value = "";
  }
  if (selectedFileUrl) URL.revokeObjectURL(selectedFileUrl);
  selectedFileUrl = file ? URL.createObjectURL(file) : "";

  const img = qs("#inference-original-img");
  const placeholder = qs("#inference-original-placeholder");
  if (img && selectedFileUrl) {
    img.src = selectedFileUrl;
    img.style.display = "block";
    if (placeholder) placeholder.style.display = "none";
  } else if (img) {
    img.style.display = "none";
    if (placeholder) placeholder.style.display = "block";
  }
  updateRunButtonState();
}

async function runInference() {
  if (!appState.currentProjectId || appState.inferenceRunning) return;
  setInferenceError("");

  if (!(appState.models || []).length) {
    await loadInferenceModels(true);
  }

  const model = ensureSelectedModel();
  if (!model) {
    updateRunButtonState();
    setInferenceError("尚未找到可用模型，請先完成訓練或按 Refresh Models。");
    return;
  }

  const files = [...(qs("#inference-image-file")?.files || [])];
  const imagePaths = parseImagePathTargets(qs("#inference-image-path")?.value);
  if (!files.length && !imagePaths.length) {
    updateRunButtonState();
    setInferenceError("請選擇一張或多張圖片，或輸入本機圖片路徑。");
    return;
  }

  appState.inferenceRunning = true;
  updateRunButtonState();
  try {
    const targets = files.length ? files : imagePaths;
    const results = [];
    const failures = [];

    for (let index = 0; index < targets.length; index += 1) {
      const target = targets[index];
      const form = buildInferenceForm(model, target, files.length > 0);
      try {
        const result = await apiFetch(`/api/projects/${appState.currentProjectId}/inference/image`, {
          method: "POST",
          body: form
        });
        results.push(result);
      } catch (err) {
        failures.push({
          name: target?.name || String(target || `image_${index + 1}`),
          message: err.message
        });
      }
    }

    if (!results.length) {
      throw new Error(failures.map((item) => `${item.name}: ${item.message}`).join("; ") || "Inference failed");
    }

    appState.inferenceLastResult = results[0];
    appState.inferenceLastBatchResults = {
      total: targets.length,
      succeeded: results.length,
      failed: failures.length,
      results,
      failures
    };
    appState.inferenceJobsProjectId = "";
    renderInferenceResult();

    if (results.some((result) => result.summary?.device_fallback)) {
      eventBus.emit("toast", "偵測不到 GPU 資源，已自動降級為 CPU 推論。");
    } else if (targets.length > 1) {
      eventBus.emit("toast", `批次推論完成：${results.length}/${targets.length}`);
    } else {
      eventBus.emit("toast", `Inference completed: ${results[0].job_id}`);
    }
  } catch (err) {
    setInferenceError(`推論失敗：${err.message}`);
  } finally {
    appState.inferenceRunning = false;
    updateRunButtonState();
  }
}

function buildInferenceForm(model, target, isFileTarget) {
  const form = new FormData();
  form.append("model_id", model.model_id);
  form.append("conf", qs("#inference-conf")?.value || "0.25");
  form.append("iou", qs("#inference-iou")?.value || "0.70");
  form.append("imgsz", qs("#inference-imgsz")?.value || "640");
  form.append("device", qs("#inference-device")?.value || "cpu");
  form.append("mask_opacity", qs("#inference-mask-opacity")?.value || "0.45");
  form.append("show_mask", String(qs("#inference-show-mask")?.checked ?? true));
  form.append("show_bbox", String(qs("#inference-show-bbox")?.checked ?? true));
  form.append("class_filter", qs("#inference-class-filter")?.value || "");
  if (isFileTarget) form.append("file", target, target.name);
  else form.append("image_path", target);
  return form;
}

function parseImagePathTargets(rawValue) {
  return String(rawValue || "")
    .split(";")
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderInferenceResult() {
  const result = appState.inferenceLastResult;
  const outputImg = qs("#inference-result-img");
  const outputPlaceholder = qs("#inference-result-placeholder");

  if (result?.urls?.annotated_image && outputImg) {
    outputImg.src = `${result.urls.annotated_image}?t=${Date.now()}`;
    outputImg.style.display = "block";
    if (outputPlaceholder) outputPlaceholder.style.display = "none";
  }

  const summary = result?.summary;
  if (!summary) {
    setHTML("#inference-summary", `<div class="empty-state">尚未執行推論。</div>`);
    setHTML("#inference-prediction-signals", "");
    return;
  }

  let fallbackHtml = "";
  if (summary.device_fallback) {
    fallbackHtml = `
      <div style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.2); border-radius: var(--radius); padding: 8px 12px; margin-top: 10px; font-size: 0.78rem; color: #f59e0b; display: flex; align-items: center; gap: 8px; font-weight: 500;">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span>偵測不到 GPU 資源，已自動降級為 CPU 推論。</span>
      </div>
    `;
  }
  const batch = appState.inferenceLastBatchResults;
  const batchHtml = batch && batch.total > 1 ? `
    <div class="path-row"><span>批次推論</span><code>${escapeHtml(`${batch.succeeded}/${batch.total} 成功`)}</code></div>
    ${batch.failures?.length ? `<div class="path-row"><span>失敗項目</span><code>${escapeHtml(batch.failures.map((item) => `${item.name}: ${item.message}`).join("; "))}</code></div>` : ""}
  ` : "";

  setHTML("#inference-summary", `
    <div class="path-row"><span>Job ID</span><code>${escapeHtml(result.job_id)}</code></div>
    ${batchHtml}
    <div class="path-row"><span>Output path</span><code>${escapeHtml(result.paths?.job_dir || "--")}</code></div>
    <div class="path-row"><span>Annotated image</span><code>${escapeHtml(result.paths?.annotated_image || "--")}</code></div>
    <div class="path-row"><span>Prediction JSON</span><code>${escapeHtml(result.paths?.prediction_json || "--")}</code></div>
    <div class="path-row"><span>Latency</span><code>${escapeHtml(summary.inference_time_ms)} ms</code></div>
    <div class="path-row"><span>Classes</span><code>${escapeHtml((summary.detected_classes || []).join(", ") || "--")}</code></div>
    ${fallbackHtml}
  `);

  setHTML("#inference-prediction-signals", `
    <div class="metric-card"><span>Mask area</span><strong>${formatPercent(summary.mask_area_ratio)}</strong></div>
    <div class="metric-card"><span>Prediction class</span><strong>${escapeHtml(summary.dominant_class || "--")}</strong></div>
    <div class="metric-card"><span>Confidence</span><strong>${formatPercent(summary.average_confidence)}</strong></div>
    <div class="metric-card"><span>Latency</span><strong>${escapeHtml(summary.inference_time_ms)} ms</strong></div>
  `);

  const viewBtn = qs("#btn-view-inference-output");
  const copyBtn = qs("#btn-copy-inference-path");
  if (viewBtn) viewBtn.disabled = false;
  if (copyBtn) copyBtn.disabled = false;
}

function updateRunButtonState() {
  const btn = qs("#btn-run-inference");
  if (!btn) return;

  const model = ensureSelectedModel();
  const hasImage = Boolean((qs("#inference-image-file")?.files?.length || 0) > 0 || qs("#inference-image-path")?.value?.trim());
  const compatible = model ? isModelCompatible(appState.currentProject?.task_type, model.task_type) : false;
  const reason = getRunDisabledReason({ model, hasImage, compatible });

  btn.disabled = Boolean(reason);
  btn.classList.toggle("btn-disabled", Boolean(reason));
  btn.innerHTML = appState.inferenceRunning
    ? `<i class="fa-solid fa-spinner fa-spin"></i> Running`
    : `<i class="fa-solid fa-play"></i> Run Inference`;

  setRunReason(reason);
}

function getRunDisabledReason({ model, hasImage, compatible }) {
  if (appState.inferenceRunning) return "推論執行中，請等待目前工作完成。";
  if (!appState.currentProjectId) return "尚未載入專案。";
  if (modelsLoading) return "正在掃描可用模型權重。";
  if (!model) return "找不到可用模型，請先完成訓練或按 Refresh Models。";
  if (!compatible) return "選擇的模型任務與目前專案任務不相容。";
  if (!hasImage) return "請上傳單張圖片，或輸入本機圖片路徑。";
  return "";
}

function setRunReason(reason) {
  const el = qs("#inference-run-reason");
  if (!el) return;
  if (reason) {
    el.textContent = reason;
    el.classList.remove("ready");
  } else {
    el.textContent = "Ready：已選擇模型與測試圖片，可以執行推論。";
    el.classList.add("ready");
  }
}

function ensureSelectedModel() {
  const models = appState.models || [];
  if (models.length && !models.some((model) => model.model_id === appState.inferenceSelectedModelId)) {
    appState.inferenceSelectedModelId = models[0].model_id;
  }
  return selectedModel();
}

function selectedModel() {
  return (appState.models || []).find((model) => model.model_id === appState.inferenceSelectedModelId) || null;
}

function isModelCompatible(projectTask = "", modelTask = "") {
  const project = String(projectTask || "").toLowerCase();
  const model = String(modelTask || "").toLowerCase();
  if (!project || !model) return true;
  if (project.includes("segmentation")) return model.includes("segmentation");
  if (project.includes("detection")) return model.includes("detection");
  if (project.includes("classification")) return model.includes("classification");
  return true;
}

function setInferenceError(message) {
  const el = qs("#inference-error");
  if (!el) return;
  if (!message) {
    el.classList.add("hidden");
    el.textContent = "";
    return;
  }
  el.classList.remove("hidden");
  el.textContent = message;
}

function formatMetric(value) {
  return value === null || value === undefined ? "--" : Number(value).toFixed(3);
}

function formatPercent(value) {
  return value === null || value === undefined ? "--" : `${(Number(value) * 100).toFixed(1)}%`;
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  if (!value) return "--";
  return String(value).replace("T", " ").slice(0, 19);
}
