import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { escapeHtml, qs, qsa } from "../utils.js";
import { openActionGuard } from "../core/action_guard.js?v=20260712-soft-action-guard";

const guideState = {
  payload: null,
  selectedId: "",
  catalogKey: "",
  loading: false,
  localRuns: [],
  report: null,
  reportTab: "summary",
};

let profileChart = null;
let benchmarkChart = null;

export function initModelGuide() {
  qs("#btn-model-guide-refresh")?.addEventListener("click", () => loadGuide({ force: true }));
  ["#model-guide-architecture", "#model-guide-objective"].forEach((selector) => {
    qs(selector)?.addEventListener("change", () => loadGuide({ force: true }));
  });
  ["#model-guide-task", "#model-guide-family"].forEach((selector) => {
    qs(selector)?.addEventListener("change", () => renderGuide());
  });
  qs("#model-guide-search")?.addEventListener("input", () => renderGuide());
  qs("#model-guide-list")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-model-guide-id]");
    if (!button) return;
    guideState.selectedId = button.dataset.modelGuideId;
    guideState.report = null;
    renderGuide();
  });
  qs("#btn-model-guide-apply")?.addEventListener("click", applySelectedModel);
  qs("#btn-model-guide-build-report")?.addEventListener("click", buildReport);
  qsa("[data-model-guide-report-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      guideState.reportTab = button.dataset.modelGuideReportTab || "summary";
      renderReport();
    });
  });
  qsa("[data-model-guide-export]").forEach((button) => {
    button.addEventListener("click", () => exportReport(button.dataset.modelGuideExport));
  });
  eventBus.on("language-changed", () => {
    if (appState.currentPage === "model-guide") renderGuide();
  });
}

export function renderModelGuidePage() {
  if (appState.currentPage !== "model-guide") return;
  const architecture = qs("#model-guide-architecture");
  if (architecture && architecture.value === "all" && appState.currentProject) {
    architecture.value = projectArchitecture();
  }
  const key = catalogKey();
  if (!guideState.payload || guideState.catalogKey !== key) void loadGuide();
  else renderGuide();
}

async function loadGuide({ force = false } = {}) {
  if (guideState.loading) return;
  const key = catalogKey();
  if (!force && guideState.payload && guideState.catalogKey === key) return;
  guideState.loading = true;
  guideState.catalogKey = key;
  setLoading();
  try {
    const architecture = qs("#model-guide-architecture")?.value || "all";
    const objective = qs("#model-guide-objective")?.value || "balanced";
    const systemParams = new URLSearchParams({ usage: "all" });
    if (architecture !== "all") systemParams.set("architecture", architecture);
    const systemPayload = await apiFetch(`/api/models/catalog?${systemParams.toString()}`, { suppressToast: true });
    guideState.payload = systemPayload;
    if (appState.currentProjectId) {
      const projectParams = new URLSearchParams({ usage: "guide", objective });
      if (architecture !== "all") projectParams.set("architecture", architecture);
      const projectPayload = await apiFetch(
        `/api/projects/${encodeURIComponent(appState.currentProjectId)}/models/catalog?${projectParams.toString()}`,
        { suppressToast: true },
      );
      const ranked = new Map((projectPayload.models || []).map((model) => [model.model_id, model]));
      guideState.payload = {
        ...systemPayload,
        project_task_family: projectPayload.task_family,
        decision_summary: projectPayload.decision_summary,
        models: (systemPayload.models || []).map((model) => ({ ...model, ...(ranked.get(model.model_id) || {}) })),
      };
    }
    await loadLocalRuns(architecture);
    renderFamilyOptions();
    const models = filteredModels();
    if (!models.some((model) => model.model_id === guideState.selectedId)) {
      guideState.selectedId = models[0]?.model_id || "";
    }
    guideState.report = null;
    renderGuide();
  } catch (error) {
    guideState.payload = null;
    qs("#model-guide-list").innerHTML = `<div class="empty-state">${escapeHtml(t("modelGuide.loadFailed", { message: error.message }))}</div>`;
  } finally {
    guideState.loading = false;
  }
}

async function loadLocalRuns(architecture) {
  guideState.localRuns = [];
  if (!appState.currentProjectId) return;
  const architectures = architecture === "all" ? ["cnn", "rnn"] : [architecture];
  const payloads = await Promise.all(architectures.map(async (kind) => {
    try {
      return await apiFetch(`/api/projects/${encodeURIComponent(appState.currentProjectId)}/compare/runs?architecture=${kind}`, { suppressToast: true });
    } catch (_error) {
      return { runs: [] };
    }
  }));
  guideState.localRuns = payloads.flatMap((item) => item.runs || []);
}

function catalogKey() {
  return [
    appState.currentProjectId || "system",
    qs("#model-guide-architecture")?.value || "all",
    qs("#model-guide-objective")?.value || "balanced",
  ].join("|");
}

function setLoading() {
  const list = qs("#model-guide-list");
  if (list) list.innerHTML = `<div class="empty-state">${escapeHtml(t("common.loading"))}</div>`;
}

function renderFamilyOptions() {
  const select = qs("#model-guide-family");
  if (!select) return;
  const previous = select.value || "all";
  const families = [...new Set((guideState.payload?.models || []).map((model) => model.model_family || model.backend || "other"))].sort();
  select.innerHTML = `<option value="all">${escapeHtml(t("common.all"))}</option>${families.map((family) => `<option value="${escapeHtml(family)}">${escapeHtml(familyLabel(family))}</option>`).join("")}`;
  select.value = families.includes(previous) ? previous : "all";
}

function filteredModels() {
  const task = qs("#model-guide-task")?.value || "all";
  const family = qs("#model-guide-family")?.value || "all";
  const search = String(qs("#model-guide-search")?.value || "").trim().toLowerCase();
  return (guideState.payload?.models || []).filter((model) => {
    const taskMatch = task === "all" || normalizeTask(model.task_family) === task;
    const familyValue = String(model.model_family || model.backend || "other");
    const familyMatch = family === "all" || familyValue === family;
    const searchText = `${model.display_name || ""} ${model.model_id || ""} ${familyValue}`.toLowerCase();
    return taskMatch && familyMatch && (!search || searchText.includes(search));
  });
}

function renderGuide() {
  if (!guideState.payload) return;
  const models = filteredModels();
  if (!models.some((model) => model.model_id === guideState.selectedId)) guideState.selectedId = models[0]?.model_id || "";
  const selected = selectedModel();
  renderContext(models);
  renderList(models);
  renderDetail(selected);
  renderDecision(selected);
  renderCharts(selected);
  renderReport();
}

function renderContext(models) {
  const gpu = guideState.payload?.hardware?.gpu || {};
  const device = (gpu.devices || [])[0] || {};
  setText("#model-guide-hardware", gpu.cuda_available ? `${device.name || "GPU"}${device.vram_total_mb ? ` · ${Math.round(device.vram_total_mb / 1024)} GB` : ""}` : t("modelSelection.cpuMode"));
  setText("#model-guide-project-context", appState.currentProject?.project_name || t("modelGuide.systemCatalog"));
  setText("#model-guide-count", String(models.length));
  setText("#model-guide-list-count", String(models.length));
}

function renderList(models) {
  const host = qs("#model-guide-list");
  if (!host) return;
  if (!models.length) {
    host.innerHTML = `<div class="empty-state">${escapeHtml(t("modelGuide.noModels"))}</div>`;
    return;
  }
  host.innerHTML = models.map((model) => {
    const metric = model.benchmark?.primary_metric;
    const status = model.source === "research" ? t("modelSelection.researchOnly") : model.usable ? t("modelSelection.ready") : model.installation_required ? t("modelSelection.installRequired") : t("modelSelection.unavailable");
    return `<button type="button" class="model-guide-list-item ${model.model_id === guideState.selectedId ? "selected" : ""}" data-model-guide-id="${escapeHtml(model.model_id)}">
      <span class="model-guide-list-heading"><strong class="no-i18n">${escapeHtml(model.display_name || model.model_id)}</strong>${model.recommended_for_project || model.recommended ? `<em>${escapeHtml(t("modelGuide.recommended"))}</em>` : ""}</span>
      <span class="no-i18n">${escapeHtml(taskLabel(model.task_family))} · ${escapeHtml(scaleLabel(model.decision_profile?.scale))}</span>
      <small>${metric ? `${escapeHtml(metric.label)} ${formatNumber(metric.value)}` : escapeHtml(t("modelSelection.profileBased"))} · ${escapeHtml(status)}</small>
    </button>`;
  }).join("");
}

function renderDetail(model) {
  const host = qs("#model-guide-detail");
  if (!host) return;
  if (!model) {
    host.innerHTML = `<div class="empty-state">${escapeHtml(t("modelGuide.selectModel"))}</div>`;
    return;
  }
  const profile = model.decision_profile || {};
  const benchmark = model.benchmark || {};
  const bestFor = localized(profile.best_for) || [];
  const tradeoffs = localized(profile.tradeoffs) || [];
  const metric = benchmark.primary_metric || {};
  host.innerHTML = `
    <div class="model-guide-detail-header">
      <div><span class="eyebrow no-i18n">${escapeHtml(familyLabel(model.model_family || model.backend))}</span><h2 class="no-i18n">${escapeHtml(model.display_name || model.model_id)}</h2></div>
      <div class="model-guide-tags"><span>${escapeHtml(taskLabel(model.task_family))}</span><span class="no-i18n">${escapeHtml(model.format || "--")}</span><span class="${model.trainable ? "success" : "warning"}">${escapeHtml(model.trainable ? t("modelGuide.trainable") : t("modelGuide.referenceOnly"))}</span></div>
    </div>
    <p class="model-guide-summary">${escapeHtml(localized(profile.summary) || t("modelSelection.noDescription"))}</p>
    <div class="model-guide-metrics">
      ${metricCard(t("modelGuide.officialMetric"), metric.value == null ? "--" : formatNumber(metric.value), metric.label || "")}
      ${metricCard(t("modelGuide.parameters"), benchmark.parameters_m ? `${formatNumber(benchmark.parameters_m)} M` : "--", "")}
      ${metricCard(t("modelGuide.modelSize"), model.download_size ? formatBytes(model.download_size) : "--", "")}
      ${metricCard(t("modelGuide.recommendedVram"), model.min_vram_mb ? `${formatNumber(model.min_vram_mb / 1024)} GB` : "--", "")}
      ${metricCard(t("modelGuide.latency"), latencyValue(benchmark), latencyRuntime(benchmark))}
    </div>
    <div class="model-guide-pros-cons">
      ${detailList(t("modelGuide.advantages"), bestFor, "advantage", "fa-thumbs-up")}
      ${detailList(t("modelGuide.limitations"), tradeoffs, "limitation", "fa-triangle-exclamation")}
    </div>
    <div class="model-guide-charts">
      <section><div class="section-title compact"><h3 data-i18n="modelGuide.modelProfile">${escapeHtml(t("modelGuide.modelProfile"))}</h3></div><div class="model-guide-chart"><canvas id="model-guide-profile-chart"></canvas></div></section>
      <section><div class="section-title compact"><h3>${escapeHtml(t("modelGuide.officialVsLocal"))}</h3></div><div class="model-guide-chart"><canvas id="model-guide-benchmark-chart"></canvas><div id="model-guide-local-empty" class="empty-state hidden"></div></div></section>
    </div>`;
}

function renderDecision(model) {
  const host = qs("#model-guide-decision");
  if (!host) return;
  if (!model) {
    host.innerHTML = `<div class="empty-state">${escapeHtml(t("modelGuide.selectModel"))}</div>`;
    return;
  }
  const runs = matchingRuns(model);
  const fit = model.hardware_fit || (model.trainable ? "unknown" : "unavailable");
  const recommendation = localized(model.decision_profile?.summary) || t("modelGuide.defaultRecommendation", { model: model.display_name || model.model_id });
  host.innerHTML = `
    <dl class="model-guide-decision-list">
      <div><dt>${escapeHtml(t("modelGuide.hardwareFit"))}</dt><dd><span class="model-fit-badge ${escapeHtml(fit)}">${escapeHtml(t(`modelSelection.fit.${fit}`))}</span></dd></div>
      <div><dt>${escapeHtml(t("modelGuide.trainingStatus"))}</dt><dd>${escapeHtml(model.trainable ? t("modelGuide.trainable") : t("modelGuide.referenceOnly"))}</dd></div>
      <div><dt>${escapeHtml(t("modelGuide.localRunCount"))}</dt><dd>${runs.length}</dd></div>
      <div><dt>${escapeHtml(t("modelSelection.license"))}</dt><dd class="no-i18n">${escapeHtml(model.license || "--")}</dd></div>
    </dl>
    <section class="model-guide-recommendation"><strong>${escapeHtml(t("modelGuide.recommendation"))}</strong><p>${escapeHtml(recommendation)}</p></section>
    ${model.source === "research" ? `<section class="model-guide-risk-note"><i class="fa-solid fa-flask"></i><span>${escapeHtml(t("modelGuide.researchWarning"))}</span></section>` : ""}`;
}

function renderCharts(model) {
  destroyCharts();
  if (!model || typeof window.Chart === "undefined") return;
  const profileCanvas = qs("#model-guide-profile-chart");
  const benchmarkCanvas = qs("#model-guide-benchmark-chart");
  if (profileCanvas) {
    profileChart = new window.Chart(profileCanvas, {
      type: "radar",
      data: {
        labels: [t("modelGuide.accuracy"), t("modelGuide.speed"), t("modelGuide.efficiency"), t("modelGuide.deploymentEase"), t("modelGuide.hardwareFit")],
        datasets: [{ label: model.display_name, data: profileScores(model), borderColor: "#3b82f6", backgroundColor: "rgba(59,130,246,.18)", pointBackgroundColor: "#3b82f6" }],
      },
      options: { responsive: true, maintainAspectRatio: false, scales: { r: { beginAtZero: true, max: 100, ticks: { display: false } } }, plugins: { legend: { display: false } } },
    });
  }
  if (!benchmarkCanvas) return;
  const official = model.benchmark?.primary_metric;
  const runs = matchingRuns(model);
  const compatibleRuns = runs.filter((run) => sameMetric(official?.key, run.primary_metric?.key));
  const empty = qs("#model-guide-local-empty");
  if (!official?.value && !compatibleRuns.length) {
    benchmarkCanvas.hidden = true;
    empty?.classList.remove("hidden");
    if (empty) empty.textContent = t("modelGuide.noComparableMetrics");
    return;
  }
  benchmarkCanvas.hidden = false;
  empty?.classList.toggle("hidden", compatibleRuns.length > 0);
  if (empty && !compatibleRuns.length) empty.textContent = t("modelGuide.noLocalRuns");
  const labels = [t("modelGuide.officialBenchmark"), ...compatibleRuns.slice(0, 3).map((run) => run.run_id)];
  const values = [Number(official?.value || 0), ...compatibleRuns.slice(0, 3).map((run) => Number(run.primary_metric?.value || 0))];
  benchmarkChart = new window.Chart(benchmarkCanvas, {
    type: "bar",
    data: { labels, datasets: [{ label: official?.label || t("modelGuide.primaryMetric"), data: values, backgroundColor: ["#3b82f6", "#22c55e", "#14b8a6", "#84cc16"], borderRadius: 3 }] },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true } }, plugins: { legend: { display: false } } },
  });
}

function buildReport() {
  const model = selectedModel();
  if (!model) return;
  const profile = model.decision_profile || {};
  const benchmark = model.benchmark || {};
  const runs = matchingRuns(model);
  guideState.report = {
    model,
    createdAt: new Date().toISOString(),
    sections: {
      summary: [localized(profile.summary) || t("modelSelection.noDescription"), ...((localized(profile.best_for) || []).map((item) => `${t("modelGuide.advantagePrefix")} ${item}`))],
      official: benchmark.primary_metric?.value == null
        ? [t("modelGuide.noOfficialBenchmark")]
        : [`${benchmark.primary_metric.label}: ${formatNumber(benchmark.primary_metric.value)}`, `${t("modelGuide.dataset")}: ${benchmark.dataset || "--"}`, `${t("modelGuide.latency")}: ${latencyValue(benchmark)}`],
      local: runs.length ? runs.map((run) => `${run.run_id}: ${run.primary_metric?.label || run.primary_metric?.key || "metric"} ${formatNumber(run.primary_metric?.value)}`) : [t("modelGuide.noLocalRuns")],
      deployment: [`${t("modelGuide.format")}: ${model.format || "--"}`, `${t("modelGuide.recommendedVram")}: ${model.min_vram_mb ? `${formatNumber(model.min_vram_mb / 1024)} GB` : "--"}`, `${t("modelSelection.license")}: ${model.license || "--"}`],
      risk: localized(profile.tradeoffs) || [t("modelGuide.noKnownRisks")],
    },
  };
  guideState.reportTab = "summary";
  renderReport();
}

function renderReport() {
  qsa("[data-model-guide-report-tab]").forEach((button) => {
    const active = button.dataset.modelGuideReportTab === guideState.reportTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  const status = qs("#model-guide-report-status");
  const host = qs("#model-guide-report-preview");
  if (!host) return;
  if (!guideState.report) {
    if (status) status.textContent = t("modelGuide.notGenerated");
    host.innerHTML = `<div class="empty-state">${escapeHtml(t("modelGuide.reportEmpty"))}</div>`;
    return;
  }
  if (status) status.textContent = t("modelGuide.generated");
  const lines = guideState.report.sections[guideState.reportTab] || [];
  host.innerHTML = `<article><header><div><span class="eyebrow">${escapeHtml(t("modelGuide.reportType"))}</span><h3 class="no-i18n">${escapeHtml(guideState.report.model.display_name)}</h3></div><time>${escapeHtml(formatDate(guideState.report.createdAt))}</time></header><ul>${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul><footer>${escapeHtml(t("modelGuide.reportSourceNote"))}</footer></article>`;
}

function exportReport(format) {
  if (!guideState.report) {
    buildReport();
    if (!guideState.report) return;
  }
  const markdown = reportMarkdown(guideState.report);
  const safeName = String(guideState.report.model.display_name || "model").replace(/[^a-z0-9_-]+/gi, "_").toLowerCase();
  if (format === "markdown") return downloadBlob(`${safeName}_selection_report.md`, markdown, "text/markdown;charset=utf-8");
  const html = reportHtml(guideState.report, markdown);
  if (format === "html") return downloadBlob(`${safeName}_selection_report.html`, html, "text/html;charset=utf-8");
  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    eventBus.emit("toast", t("modelGuide.popupBlocked"));
    return;
  }
  printWindow.opener = null;
  printWindow.document.write(html);
  printWindow.document.close();
  printWindow.focus();
  printWindow.print();
}

function applySelectedModel() {
  const model = selectedModel();
  if (!model) return;
  if (!appState.currentProjectId) {
    openActionGuard({ title: t("modelGuide.applyTraining"), reasons: [t("actionGuard.reason.project")], actions: [["projects", "actionGuard.newProject"]] });
    return;
  }
  if (!model.trainable) {
    openActionGuard({ title: model.display_name, reasons: [t("modelGuide.notTrainableReason")], actions: [] });
    return;
  }
  eventBus.emit("navigate", "training");
  window.setTimeout(() => {
    const isRnn = model.architecture === "rnn";
    const selector = qs(isRnn ? "#rnn-model-family" : "#train-model");
    const candidates = isRnn ? [model.selector_value, model.model_id] : [model.training_value, model.weight, model.model_id];
    const value = candidates.find((candidate) => candidate && [...(selector?.options || [])].some((option) => option.value === candidate));
    if (selector && value) {
      selector.value = value;
      selector.dispatchEvent(new Event("change", { bubbles: true }));
      eventBus.emit("toast", t("modelSelection.applied", { model: model.display_name || model.model_id }));
    }
  }, 0);
}

function selectedModel() {
  return (guideState.payload?.models || []).find((model) => model.model_id === guideState.selectedId) || null;
}

function matchingRuns(model) {
  const candidates = [model.model_id, model.display_name, model.weight, model.selector_value, model.training_value, model.model_family]
    .filter(Boolean).map(normalizeName);
  return guideState.localRuns.filter((run) => {
    const runModel = normalizeName(run.model || "");
    return runModel && candidates.some((candidate) => candidate.length > 2 && (runModel.includes(candidate) || candidate.includes(runModel)));
  });
}

function profileScores(model) {
  const profile = model.decision_profile?.profile_scores || {};
  const benchmark = model.benchmark || {};
  const latency = benchmark.latency?.gpu_ms ?? benchmark.latency?.cpu_onnx_ms;
  const parameters = Number(benchmark.parameters_m || 0);
  const quality = Number(benchmark.primary_metric?.value || profile.baseline_strength || 50);
  const fitScores = { excellent: 95, good: 80, marginal: 55, unavailable: 20, unknown: 50 };
  return [
    clamp(quality > 1 ? quality * 1.6 : quality * 100),
    Number(profile.speed || (latency ? clamp(100 - Math.log10(latency + 1) * 35) : 55)),
    Number(profile.efficiency || (parameters ? clamp(100 - Math.log10(parameters + 1) * 32) : 55)),
    deploymentScore(model),
    fitScores[model.hardware_fit] || 50,
  ];
}

function deploymentScore(model) {
  if (model.backend === "ultralytics_yolo") return 90;
  if (model.backend === "ultralytics_rtdetr") return 75;
  if (model.architecture === "rnn" && model.trainable) return 70;
  return model.trainable ? 60 : 30;
}

function metricCard(label, value, note) {
  return `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${note ? `<small class="no-i18n">${escapeHtml(note)}</small>` : ""}</div>`;
}

function detailList(title, values, tone, icon) {
  const items = values?.length ? values : [t("modelGuide.notDocumented")];
  return `<section class="model-guide-detail-list ${tone}"><h3><i class="fa-solid ${icon}"></i> ${escapeHtml(title)}</h3><ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>`;
}

function reportMarkdown(report) {
  const headings = { summary: t("modelGuide.reportSummary"), official: t("modelGuide.officialBenchmark"), local: t("modelGuide.localRuns"), deployment: t("modelGuide.deployment"), risk: t("modelGuide.risks") };
  const lines = [`# ${report.model.display_name} - ${t("modelGuide.reportType")}`, "", `${t("modelGuide.generatedAt")}: ${formatDate(report.createdAt)}`, ""];
  Object.entries(report.sections).forEach(([key, items]) => {
    lines.push(`## ${headings[key]}`, "", ...items.map((item) => `- ${item}`), "");
  });
  lines.push(t("modelGuide.reportSourceNote"), "");
  return lines.join("\n");
}

function reportHtml(report, markdown) {
  const body = markdown.split("\n").map((line) => {
    if (line.startsWith("# ")) return `<h1>${escapeHtml(line.slice(2))}</h1>`;
    if (line.startsWith("## ")) return `<h2>${escapeHtml(line.slice(3))}</h2>`;
    if (line.startsWith("- ")) return `<li>${escapeHtml(line.slice(2))}</li>`;
    return line ? `<p>${escapeHtml(line)}</p>` : "";
  }).join("");
  return `<!doctype html><html lang="zh-TW"><head><meta charset="utf-8"><title>${escapeHtml(report.model.display_name)} Report</title><style>body{font:14px Arial,sans-serif;max-width:900px;margin:40px auto;color:#172033;line-height:1.6}h1,h2{color:#111827}li{margin:5px 0}@media print{body{margin:18mm}}</style></head><body>${body}</body></html>`;
}

function downloadBlob(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function destroyCharts() {
  profileChart?.destroy();
  benchmarkChart?.destroy();
  profileChart = null;
  benchmarkChart = null;
}

function localized(value) {
  if (value == null || typeof value === "string" || Array.isArray(value)) return value;
  const language = appState.settings.language === "en" ? "en" : "zh-TW";
  return value[language] ?? value.en ?? Object.values(value)[0];
}

function normalizeTask(value) {
  const task = String(value || "").toLowerCase();
  if (task.includes("seg")) return "segmentation";
  if (task.includes("detect")) return "detection";
  if (task.includes("regression")) return "sequence_regression";
  if (task.includes("sequence") || task.includes("classification")) return "sequence_classification";
  return task;
}

function taskLabel(value) {
  const key = normalizeTask(value);
  const labels = { detection: t("modelSetup.detection"), segmentation: t("modelSetup.segmentation"), sequence_classification: t("modelGuide.sequenceClassification"), sequence_regression: t("modelGuide.sequenceRegression") };
  return labels[key] || value || "--";
}

function familyLabel(value) {
  const labels = { yolo26: "YOLO26", yolo11: "YOLO11", yolov8: "YOLOv8", rtdetr: "RT-DETR", "rf-detr": "RF-DETR", lstm: "LSTM", gru: "GRU", bilstm: "BiLSTM", xgboost: "XGBoost" };
  return labels[value] || value || "Other";
}

function scaleLabel(value) {
  const labels = { nano: "Nano", small: "Small", medium: "Medium", large: "Large", xlarge: "X-Large", standard: "Standard", planned: "Planned" };
  return labels[value] || value || "--";
}

function latencyValue(benchmark) {
  const value = benchmark.latency?.gpu_ms ?? benchmark.latency?.cpu_onnx_ms;
  return value == null ? "--" : `${formatNumber(value)} ms`;
}

function latencyRuntime(benchmark) {
  return benchmark.latency?.gpu_runtime || (benchmark.latency?.cpu_onnx_ms ? "CPU ONNX" : "");
}

function sameMetric(a, b) {
  const left = String(a || "").replace(/[^a-z0-9]/gi, "").toLowerCase();
  const right = String(b || "").replace(/[^a-z0-9]/gi, "").toLowerCase();
  return left && right && (left === right || left.includes(right) || right.includes(left));
}

function normalizeName(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return number >= 100 ? number.toFixed(0) : number.toFixed(number < 10 ? 2 : 1).replace(/\.0$/, "");
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  return bytes ? `${formatNumber(bytes / 1024 / 1024)} MB` : "--";
}

function formatDate(value) {
  try { return new Date(value).toLocaleString(appState.settings.language === "en" ? "en-US" : "zh-TW"); } catch (_error) { return value; }
}

function clamp(value) {
  return Math.max(0, Math.min(100, Number(value || 0)));
}

function projectArchitecture() {
  const task = String(appState.currentProject?.task_type || "").toLowerCase();
  return task.includes("sequence") || task.includes("rnn") ? "rnn" : "cnn";
}

function setText(selector, value) {
  const node = qs(selector);
  if (node) node.textContent = value;
}
