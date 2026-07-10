import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { escapeHtml, qs, qsa } from "../utils.js";

let payload = null;
let activeTab = "recommended";
let selectedModelId = "";
let selectionChart = null;

export function initModelSelectionCenter() {
  qs("#btn-open-model-selection-center")?.addEventListener("click", openModelSelectionCenter);
  qs("#btn-rnn-open-model-selection-center")?.addEventListener("click", openModelSelectionCenter);
  qs("#btn-close-model-selection")?.addEventListener("click", closeModelSelectionCenter);
  qs("#model-selection-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "model-selection-modal") closeModelSelectionCenter();
  });
  qs("#model-selection-objective")?.addEventListener("change", () => loadCandidates());
  qs("#model-selection-list")?.addEventListener("change", handleCandidateSelection);
  qsa("[data-model-selection-tab]").forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.modelSelectionTab));
  });
  qs("#btn-model-selection-apply")?.addEventListener("click", applySelectedModel);
  qs("#btn-model-selection-import")?.addEventListener("click", () => {
    closeModelSelectionCenter();
    eventBus.emit("open-model-import", { taskFamily: payload?.task_family || "" });
  });
  qs("#btn-model-selection-manage")?.addEventListener("click", () => {
    closeModelSelectionCenter();
    eventBus.emit("open-model-setup");
  });
  eventBus.on("language-changed", () => {
    if (!qs("#model-selection-modal")?.hidden && payload) renderModelSelectionCenter();
  });
}

async function openModelSelectionCenter() {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", t("modelSelection.noProject"));
    return;
  }
  const modal = qs("#model-selection-modal");
  if (!modal) return;
  modal.hidden = false;
  activeTab = "recommended";
  selectedModelId = "";
  setLoadingState();
  await loadCandidates();
}

function closeModelSelectionCenter() {
  const modal = qs("#model-selection-modal");
  if (modal) modal.hidden = true;
  destroyChart();
}

async function loadCandidates() {
  const architecture = projectArchitecture();
  const objective = qs("#model-selection-objective")?.value || "balanced";
  setLoadingState();
  try {
    payload = await apiFetch(
      `/api/projects/${encodeURIComponent(appState.currentProjectId)}/models/catalog?architecture=${architecture}&usage=train&objective=${objective}`,
      { suppressToast: true },
    );
    const candidates = visibleModels();
    if (!candidates.some((model) => model.model_id === selectedModelId)) {
      selectedModelId = candidates[0]?.model_id || "";
    }
    renderModelSelectionCenter();
  } catch (error) {
    payload = null;
    qs("#model-selection-list").innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(t("modelSelection.loadFailed", { message: error.message }))}</td></tr>`;
    qs("#model-selection-detail").innerHTML = `<div class="empty-state">${escapeHtml(t("modelSelection.loadFailed", { message: error.message }))}</div>`;
    renderChart([]);
  }
}

function projectArchitecture() {
  const task = String(appState.currentProject?.task_type || "").toLowerCase();
  return task.includes("sequence") || task.includes("rnn") ? "rnn" : "cnn";
}

function setLoadingState() {
  const list = qs("#model-selection-list");
  if (list) list.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(t("common.loading"))}</td></tr>`;
  const detail = qs("#model-selection-detail");
  if (detail) detail.innerHTML = `<div class="empty-state">${escapeHtml(t("common.loading"))}</div>`;
}

function setActiveTab(nextTab) {
  activeTab = nextTab || "recommended";
  qsa("[data-model-selection-tab]").forEach((button) => {
    const active = button.dataset.modelSelectionTab === activeTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  const candidates = visibleModels();
  selectedModelId = candidates.some((model) => model.model_id === selectedModelId)
    ? selectedModelId
    : candidates[0]?.model_id || "";
  renderModelSelectionCenter();
}

function visibleModels() {
  const models = payload?.models || [];
  if (activeTab === "recommended") return models.filter((model) => model.recommended_for_project);
  if (activeTab === "custom") {
    return models.filter((model) => ["user_import", "imported", "project_trained"].includes(String(model.source || "")));
  }
  return models;
}

function renderModelSelectionCenter() {
  if (!payload) return;
  renderContext();
  const candidates = visibleModels();
  const count = qs("#model-selection-count");
  if (count) count.textContent = String(candidates.length);
  renderCandidateTable(candidates);
  renderChart(candidates);
  renderDetail(candidates.find((model) => model.model_id === selectedModelId));
}

function renderContext() {
  setNodeText("#model-selection-task", taskLabel(payload.task_family));
  setNodeText("#model-selection-samples", t("modelSelection.sampleCount", { count: payload.decision_summary?.sample_count || 0 }));
  const gpu = payload.hardware?.gpu || {};
  const device = (gpu.devices || [])[0] || {};
  const hardware = gpu.cuda_available
    ? `${device.name || "GPU"}${device.vram_total_mb ? ` · ${Math.round(device.vram_total_mb / 1024)} GB` : ""}`
    : t("modelSelection.cpuMode");
  setNodeText("#model-selection-hardware", hardware);
}

function renderCandidateTable(candidates) {
  const list = qs("#model-selection-list");
  if (!list) return;
  if (!candidates.length) {
    const key = activeTab === "custom" ? "modelSelection.customEmpty" : "modelSelection.empty";
    list.innerHTML = `<tr><td colspan="6" class="empty-state">${escapeHtml(t(key))}</td></tr>`;
    return;
  }
  list.innerHTML = candidates.map((model) => {
    const benchmark = model.benchmark || {};
    const metric = benchmark.primary_metric;
    const latency = benchmark.latency?.cpu_onnx_ms;
    const fit = model.hardware_fit || "unavailable";
    const status = model.usable ? t("modelSelection.ready") : model.installation_required ? t("modelSelection.installRequired") : t("modelSelection.unavailable");
    return `
      <tr class="${model.model_id === selectedModelId ? "selected" : ""}">
        <td><input type="radio" name="model-selection-candidate" value="${escapeHtml(model.model_id)}" ${model.model_id === selectedModelId ? "checked" : ""}></td>
        <td><strong>${escapeHtml(model.display_name || model.model_id)}</strong><small>${escapeHtml(status)}</small></td>
        <td>${metric ? `${escapeHtml(metric.label)} <strong>${formatNumber(metric.value)}</strong>` : escapeHtml(t("modelSelection.profileBased"))}</td>
        <td>${latency ? `${formatNumber(latency)} ms` : "--"}</td>
        <td>${benchmark.parameters_m ? `${formatNumber(benchmark.parameters_m)} M` : "--"}</td>
        <td><span class="model-fit-badge ${escapeHtml(fit)}">${escapeHtml(t(`modelSelection.fit.${fit}`))}</span></td>
      </tr>`;
  }).join("");
}

function handleCandidateSelection(event) {
  if (event.target.name !== "model-selection-candidate") return;
  selectedModelId = event.target.value;
  renderModelSelectionCenter();
}

function renderDetail(model) {
  const detail = qs("#model-selection-detail");
  if (!detail) return;
  if (!model) {
    detail.innerHTML = activeTab === "custom"
      ? renderCustomSupport()
      : `<div class="empty-state">${escapeHtml(t("modelSelection.selectPrompt"))}</div>`;
    return;
  }
  const profile = model.decision_profile || {};
  const benchmark = model.benchmark || {};
  const bestFor = localized(profile.best_for) || [];
  const tradeoffs = localized(profile.tradeoffs) || [];
  const reasons = (model.decision_reasons || []).slice(0, 3).map((reason) => t(`modelSelection.reason.${reason}`));
  detail.innerHTML = `
    <div class="model-selection-detail-heading">
      <div><span class="eyebrow">#${model.recommendation_rank || "--"}</span><h3>${escapeHtml(model.display_name || model.model_id)}</h3></div>
      <span class="model-selection-score">${escapeHtml(t("modelSelection.score", { score: formatNumber(model.decision_score) }))}</span>
    </div>
    <p>${escapeHtml(localized(profile.summary) || t("modelSelection.noDescription"))}</p>
    <dl class="model-selection-facts">
      <div><dt>${escapeHtml(t("modelSelection.source"))}</dt><dd>${escapeHtml(sourceLabel(model.source))}</dd></div>
      <div><dt>${escapeHtml(t("modelSelection.task"))}</dt><dd>${escapeHtml(taskLabel(model.task_family))}</dd></div>
      <div><dt>${escapeHtml(t("modelSelection.license"))}</dt><dd>${escapeHtml(model.license || "--")}</dd></div>
      <div><dt>${escapeHtml(t("modelSelection.status"))}</dt><dd>${escapeHtml(model.usable ? t("modelSelection.ready") : t("modelSelection.installRequired"))}</dd></div>
    </dl>
    ${renderDetailList(t("modelSelection.recommendationReasons"), reasons)}
    ${renderDetailList(t("modelSelection.bestFor"), bestFor)}
    ${renderDetailList(t("modelSelection.tradeoffs"), tradeoffs, "risk")}
    ${benchmark.source_url ? `<a class="model-selection-source-link" href="${escapeHtml(benchmark.source_url)}" target="_blank" rel="noreferrer"><i class="fa-solid fa-arrow-up-right-from-square"></i> ${escapeHtml(t("modelSelection.officialSource"))}</a>` : ""}`;
}

function renderDetailList(title, values, tone = "") {
  if (!values?.length) return "";
  return `<section class="model-selection-detail-list ${tone}"><strong>${escapeHtml(title)}</strong><ul>${values.map((value) => `<li>${escapeHtml(value)}</li>`).join("")}</ul></section>`;
}

function renderCustomSupport() {
  return `
    <div class="model-selection-custom-support">
      <h3>${escapeHtml(t("modelSelection.customSupportTitle"))}</h3>
      <p>${escapeHtml(t("modelSelection.customSupportNote"))}</p>
      <ul>
        <li><strong>YOLO .pt</strong><span>${escapeHtml(t("modelSelection.customYoloPt"))}</span></li>
        <li><strong>YOLO .yaml</strong><span>${escapeHtml(t("modelSelection.customYoloYaml"))}</span></li>
        <li><strong>ONNX</strong><span>${escapeHtml(t("modelSelection.customOnnx"))}</span></li>
        <li><strong>RNN package</strong><span>${escapeHtml(t("modelSelection.customRnn"))}</span></li>
      </ul>
    </div>`;
}

function renderChart(candidates) {
  destroyChart();
  const canvas = qs("#model-selection-chart");
  const empty = qs("#model-selection-chart-empty");
  const note = qs("#model-selection-chart-note");
  if (!canvas || !empty) return;
  if (typeof window.Chart === "undefined" || !candidates.length) {
    canvas.hidden = true;
    empty.hidden = false;
    empty.textContent = t("modelSelection.chartEmpty");
    if (note) note.textContent = "";
    return;
  }
  canvas.hidden = false;
  empty.hidden = true;
  if (projectArchitecture() === "rnn") {
    renderRnnProfileChart(canvas, candidates.slice(0, 4));
    setNodeText("#model-selection-benchmark-kind", t("modelSelection.profileChart"));
    if (note) note.textContent = t("modelSelection.profileDisclaimer");
  } else {
    const benchmarkModels = candidates.filter((model) => model.benchmark?.primary_metric?.value && model.benchmark?.latency?.cpu_onnx_ms);
    if (!benchmarkModels.length) {
      canvas.hidden = true;
      empty.hidden = false;
      empty.textContent = t("modelSelection.chartEmpty");
      return;
    }
    renderCnnBenchmarkChart(canvas, benchmarkModels);
    setNodeText("#model-selection-benchmark-kind", t("modelSelection.officialBenchmark"));
    if (note) note.textContent = t("modelSelection.cnnChartNote");
  }
}

function renderCnnBenchmarkChart(canvas, models) {
  selectionChart = new window.Chart(canvas, {
    type: "scatter",
    data: {
      datasets: models.map((model, index) => ({
        label: model.display_name,
        data: [{ x: model.benchmark.latency.cpu_onnx_ms, y: model.benchmark.primary_metric.value }],
        pointRadius: Math.max(5, Math.min(12, 4 + Number(model.benchmark.parameters_m || 0) / 4)),
        backgroundColor: chartColor(index),
      })),
    },
    options: chartOptions(t("modelSelection.cpuLatencyAxis"), t("modelSelection.qualityAxis")),
  });
}

function renderRnnProfileChart(canvas, models) {
  const keys = ["speed", "efficiency", "temporal_context", "baseline_strength"];
  selectionChart = new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: keys.map((key) => t(`modelSelection.profile.${key}`)),
      datasets: models.map((model, index) => ({
        label: model.display_name,
        data: keys.map((key) => Number(model.decision_profile?.profile_scores?.[key] || 0)),
        backgroundColor: chartColor(index),
        borderRadius: 3,
      })),
    },
    options: { ...chartOptions("", t("modelSelection.relativeScoreAxis")), scales: { x: { grid: { display: false } }, y: { beginAtZero: true, max: 100 } } },
  });
}

function chartOptions(xTitle, yTitle) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
    scales: {
      x: { title: { display: Boolean(xTitle), text: xTitle } },
      y: { beginAtZero: false, title: { display: Boolean(yTitle), text: yTitle } },
    },
  };
}

function destroyChart() {
  if (selectionChart) selectionChart.destroy();
  selectionChart = null;
}

function applySelectedModel() {
  const model = (payload?.models || []).find((item) => item.model_id === selectedModelId);
  if (!model) {
    eventBus.emit("toast", t("modelSelection.selectPrompt"));
    return;
  }
  if (!model.usable) {
    eventBus.emit("toast", t("modelSelection.requiresSetup", { model: model.display_name || model.model_id }));
    closeModelSelectionCenter();
    eventBus.emit("open-model-setup");
    return;
  }
  const isRnn = projectArchitecture() === "rnn";
  if (isRnn) {
    const taskHead = qs("#rnn-task-head");
    const expectedHead = String(model.task_family || "").includes("regression") ? "regression" : "classification";
    if (taskHead && taskHead.value !== expectedHead) {
      taskHead.value = expectedHead;
      taskHead.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }
  const selector = isRnn ? qs("#rnn-model-family") : qs("#train-model");
  const candidateValues = isRnn
    ? [model.model_id, model.selector_value].filter(Boolean)
    : [model.training_value, model.model_id].filter(Boolean);
  const value = candidateValues.find((candidate) => [...(selector?.options || [])].some((option) => option.value === candidate));
  if (!selector || !value) {
    eventBus.emit("toast", t("modelSelection.applyUnavailable"));
    return;
  }
  selector.value = value;
  selector.dispatchEvent(new Event("change", { bubbles: true }));
  closeModelSelectionCenter();
  eventBus.emit("toast", t("modelSelection.applied", { model: model.display_name || model.model_id }));
}

function localized(value) {
  if (value == null || typeof value === "string" || Array.isArray(value)) return value;
  const language = appState.settings.language === "en" ? "en" : "zh-TW";
  return value[language] ?? value.en ?? Object.values(value)[0];
}

function taskLabel(task) {
  const normalized = String(task || "unknown").toLowerCase();
  if (normalized.includes("seg")) return t("modelSelection.taskLabel.segmentation");
  if (normalized.includes("detect")) return t("modelSelection.taskLabel.detection");
  if (normalized.includes("sequence") && normalized.includes("regression")) return t("modelSelection.taskLabel.sequence_regression");
  if (normalized.includes("sequence")) return t("modelSelection.taskLabel.sequence_classification");
  return t("modelSelection.taskLabel.unknown");
}

function sourceLabel(source) {
  const normalized = String(source || "unknown").toLowerCase();
  return t(`modelSelection.sourceLabel.${normalized}`);
}

function setNodeText(selector, value) {
  const node = qs(selector);
  if (node) node.textContent = value;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return number >= 100 ? number.toFixed(0) : number.toFixed(number < 10 ? 2 : 1).replace(/\.0$/, "");
}

function chartColor(index) {
  return ["#3b82f6", "#22c55e", "#f59e0b", "#8b5cf6", "#06b6d4", "#ef4444"][index % 6];
}
