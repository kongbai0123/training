import { appState } from "../state.js";
import { eventBus } from "../event_bus.js";
import { apiFetch } from "../api.js";
import { qs, qsa, escapeHtml, setText } from "../utils.js";

const compareState = {
  architecture: "cnn",
  loadingRuns: false,
  comparing: false,
  runs: [],
  selectedRuns: [],
  baselineRunId: null,
  result: null,
  activeMetricKey: null,
  loadedProjectId: "",
  outputComparing: false,
  outputResult: null,
  reportExporting: false,
  reportResult: null,
  reportLoading: false,
  reportHistory: [],
};

let trendChart = null;

export function initModelCompare() {
  qsa("[data-compare-architecture]").forEach((button) => {
    button.addEventListener("click", () => {
      const architecture = button.dataset.compareArchitecture || "cnn";
      setCompareArchitecture(architecture);
    });
  });

  qs("#btn-compare-refresh")?.addEventListener("click", () => loadComparableRuns({ force: true }));
  qs("#btn-run-compare")?.addEventListener("click", runComparison);
  qs("#btn-run-output-compare")?.addEventListener("click", runOutputComparison);
  qs("#btn-export-compare-report")?.addEventListener("click", exportCompareReport);
  qs("#compare-output-image-file")?.addEventListener("change", () => {
    compareState.outputResult = null;
    renderModelComparePage();
  });

  eventBus.on("project-deleted", () => resetCompareState());
  eventBus.on("set-compare-architecture", (architecture) => setCompareArchitecture(architecture || "cnn"));
}

export function renderModelComparePage() {
  const page = qs("#page-model-compare");
  if (!page) return;

  const isActive = appState.currentPage === "model-compare";
  if (isActive && appState.currentProjectId && compareState.loadedProjectId !== appState.currentProjectId && !compareState.loadingRuns) {
    loadComparableRuns({ force: true });
    loadCompareReports({ force: true });
  }

  renderModeControls();
  renderCompareAlert();
  renderRunList();
  renderSelectedTray();
  renderDecisionSummary();
  renderChartTabs();
  renderTrendChart();
  renderOutputComparison();
  renderConfigDiff();
  renderCompareReport();
  updateCompareActions();
}

function setCompareArchitecture(architecture) {
  const next = architecture === "rnn" ? "rnn" : "cnn";
  if (compareState.architecture === next) return;
  compareState.architecture = next;
  compareState.selectedRuns = [];
  compareState.baselineRunId = null;
  compareState.result = null;
  compareState.activeMetricKey = null;
  compareState.runs = [];
  compareState.loadedProjectId = "";
  compareState.outputResult = null;
  compareState.reportResult = null;
  compareState.reportHistory = [];
  loadComparableRuns({ force: true });
  loadCompareReports({ force: true });
  renderModelComparePage();
}

async function loadComparableRuns({ force = false } = {}) {
  if (!appState.currentProjectId) {
    resetCompareState();
    renderModelComparePage();
    return;
  }
  if (compareState.loadingRuns && !force) return;
  compareState.loadingRuns = true;
  renderModelComparePage();

  try {
    const payload = await apiFetch(`/api/projects/${encodeURIComponent(appState.currentProjectId)}/compare/runs?architecture=${encodeURIComponent(compareState.architecture)}`);
    compareState.runs = Array.isArray(payload.runs) ? payload.runs : [];
    compareState.selectedRuns = compareState.selectedRuns.filter((runId) => compareState.runs.some((run) => run.run_id === runId));
    if (compareState.baselineRunId && !compareState.selectedRuns.includes(compareState.baselineRunId)) {
      compareState.baselineRunId = compareState.selectedRuns[0] || null;
    }
    compareState.loadedProjectId = appState.currentProjectId;
    compareState.result = null;
    compareState.activeMetricKey = null;
    compareState.outputResult = null;
    compareState.reportResult = null;
  } catch (err) {
    compareState.runs = [];
    compareState.result = null;
    eventBus.emit("toast", `Failed to load comparable runs: ${err.message}`);
  } finally {
    compareState.loadingRuns = false;
    renderModelComparePage();
  }
}

async function loadCompareReports({ force = false } = {}) {
  if (!appState.currentProjectId) {
    compareState.reportHistory = [];
    return;
  }
  if (compareState.reportLoading && !force) return;
  compareState.reportLoading = true;
  renderModelComparePage();
  try {
    const payload = await apiFetch(`/api/projects/${encodeURIComponent(appState.currentProjectId)}/compare/reports`);
    compareState.reportHistory = Array.isArray(payload.reports) ? payload.reports : [];
  } catch (err) {
    compareState.reportHistory = [];
    eventBus.emit("toast", `Failed to load compare reports: ${err.message}`);
  } finally {
    compareState.reportLoading = false;
    renderModelComparePage();
  }
}

async function runComparison() {
  if (!appState.currentProjectId || compareState.selectedRuns.length < 2 || compareState.selectedRuns.length > 4) return;

  compareState.comparing = true;
  renderModelComparePage();
  try {
    const payload = await apiFetch(`/api/projects/${encodeURIComponent(appState.currentProjectId)}/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        architecture: compareState.architecture,
        run_ids: compareState.selectedRuns,
        baseline_run_id: compareState.baselineRunId || compareState.selectedRuns[0],
      }),
    });
    compareState.result = payload;
    compareState.activeMetricKey = firstMetricKey(payload);
    compareState.reportResult = null;
  } catch (err) {
    compareState.result = null;
    eventBus.emit("toast", `Compare failed: ${err.message}`);
  } finally {
    compareState.comparing = false;
    renderModelComparePage();
  }
}

async function deleteCompareReport(reportId) {
  if (!appState.currentProjectId || !reportId) return;
  try {
    await apiFetch(`/api/projects/${encodeURIComponent(appState.currentProjectId)}/compare/reports/${encodeURIComponent(reportId)}`, {
      method: "DELETE",
    });
    if (compareState.reportResult?.report_id === reportId) compareState.reportResult = null;
    await loadCompareReports({ force: true });
    eventBus.emit("toast", "Compare report deleted.");
  } catch (err) {
    eventBus.emit("toast", `Delete report failed: ${err.message}`);
  }
}

async function exportCompareReport() {
  if (!appState.currentProjectId || !compareState.result || compareState.reportExporting) return;

  compareState.reportExporting = true;
  renderModelComparePage();
  try {
    compareState.reportResult = await apiFetch(`/api/projects/${encodeURIComponent(appState.currentProjectId)}/compare/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        architecture: compareState.architecture,
        run_ids: compareState.selectedRuns,
        baseline_run_id: compareState.baselineRunId || compareState.selectedRuns[0],
      }),
    });
    eventBus.emit("toast", "Compare report exported.");
    await loadCompareReports({ force: true });
  } catch (err) {
    compareState.reportResult = null;
    eventBus.emit("toast", `Export report failed: ${err.message}`);
  } finally {
    compareState.reportExporting = false;
    renderModelComparePage();
  }
}

async function runOutputComparison() {
  if (!appState.currentProjectId || compareState.selectedRuns.length < 2 || compareState.selectedRuns.length > 4) return;
  if (compareState.architecture !== "cnn") {
    eventBus.emit("toast", "RNN output comparison is not enabled in this phase.");
    return;
  }
  const file = qs("#compare-output-image-file")?.files?.[0];
  if (!file) {
    eventBus.emit("toast", "Please upload one test image for output comparison.");
    return;
  }

  compareState.outputComparing = true;
  compareState.outputResult = null;
  renderModelComparePage();

  try {
    const form = new FormData();
    form.append("run_ids_json", JSON.stringify(compareState.selectedRuns));
    form.append("conf", qs("#compare-output-conf")?.value || "0.25");
    form.append("iou", qs("#compare-output-iou")?.value || "0.70");
    form.append("imgsz", qs("#compare-output-imgsz")?.value || "640");
    form.append("device", qs("#compare-output-device")?.value || "cpu");
    form.append("file", file);
    compareState.outputResult = await apiFetch(`/api/projects/${encodeURIComponent(appState.currentProjectId)}/compare/output-image`, {
      method: "POST",
      body: form,
    });
  } catch (err) {
    compareState.outputResult = null;
    eventBus.emit("toast", `Output compare failed: ${err.message}`);
  } finally {
    compareState.outputComparing = false;
    renderModelComparePage();
  }
}

function resetCompareState() {
  compareState.runs = [];
  compareState.selectedRuns = [];
  compareState.baselineRunId = null;
  compareState.result = null;
  compareState.activeMetricKey = null;
  compareState.loadedProjectId = "";
  compareState.outputResult = null;
  compareState.reportResult = null;
  compareState.reportHistory = [];
}

function toggleRun(runId) {
  const exists = compareState.selectedRuns.includes(runId);
  if (exists) {
    compareState.selectedRuns = compareState.selectedRuns.filter((id) => id !== runId);
    if (compareState.baselineRunId === runId) compareState.baselineRunId = compareState.selectedRuns[0] || null;
  } else {
    if (compareState.selectedRuns.length >= 4) {
      eventBus.emit("toast", "Compare supports at most 4 runs.");
      return;
    }
    compareState.selectedRuns.push(runId);
    if (!compareState.baselineRunId) compareState.baselineRunId = runId;
  }
  compareState.result = null;
  compareState.activeMetricKey = null;
  compareState.outputResult = null;
  compareState.reportResult = null;
  renderModelComparePage();
}

function setBaseline(runId) {
  if (!compareState.selectedRuns.includes(runId)) return;
  compareState.baselineRunId = runId;
  compareState.result = null;
  compareState.outputResult = null;
  compareState.reportResult = null;
  renderModelComparePage();
}

function renderModeControls() {
  qsa("[data-compare-architecture]").forEach((button) => {
    button.classList.toggle("active", button.dataset.compareArchitecture === compareState.architecture);
  });
  setText("#compare-mode-badge", compareState.architecture === "cnn" ? "CNN / YOLO" : "RNN / Sequence");
  setText(
    "#compare-mode-note",
    compareState.architecture === "cnn"
      ? "Completed CNN / YOLO runs can be compared by metrics, settings, and image output overlays."
      : "Completed RNN / Sequence runs can be compared by Loss, Accuracy, Macro-F1, MAE, RMSE, and settings. Sequence output compare remains gated."
  );
}

function renderCompareAlert() {
  const alert = qs("#compare-alert");
  if (!alert) return;
  const warnings = compareState.result?.summary?.warnings || compareState.result?.recommendation?.warnings || [];
  const messages = [];
  if (!appState.currentProjectId) messages.push("Open a project before comparing training runs.");
  if (compareState.architecture === "rnn") messages.push("RNN metric comparison is enabled for completed RNN runs. Sequence output comparison is still disabled.");
  if (warnings.length) messages.push(...warnings.slice(0, 3));
  alert.classList.toggle("hidden", messages.length === 0);
  alert.innerHTML = messages.map((message) => `<div>${escapeHtml(message)}</div>`).join("");
}

function renderRunList() {
  const host = qs("#compare-run-list");
  if (!host) return;
  setText("#compare-run-count", compareState.loadingRuns ? "Loading" : `${compareState.runs.length} runs`);

  if (!appState.currentProjectId) {
    host.innerHTML = `<div class="empty-state">Open a project to compare training runs.</div>`;
    return;
  }
  if (compareState.loadingRuns) {
    host.innerHTML = `<div class="empty-state">Loading comparable runs...</div>`;
    return;
  }
  if (!compareState.runs.length) {
    host.innerHTML = `<div class="empty-state">No completed ${escapeHtml(compareState.architecture.toUpperCase())} runs are available for comparison.</div>`;
    return;
  }

  host.innerHTML = compareState.runs.map((run) => {
    const selected = compareState.selectedRuns.includes(run.run_id);
    const primary = run.primary_metric || {};
    const value = primary.value == null ? "--" : Number(primary.value).toFixed(3);
    return `
      <article class="compare-run-card ${selected ? "selected" : ""}">
        <div>
          <strong>${escapeHtml(run.run_id)}</strong>
          <span>${escapeHtml(run.model || "--")} · ${escapeHtml(run.task_family || run.task_type || "--")}</span>
        </div>
        <div class="compare-run-meta">
          <span>${escapeHtml(primary.display_name || "Primary")}</span>
          <b>${escapeHtml(value)}</b>
        </div>
        <button type="button" class="btn btn-sm ${selected ? "btn-secondary" : "btn-primary"}" data-compare-toggle-run="${escapeHtml(run.run_id)}">
          ${selected ? "Remove" : "Add"}
        </button>
      </article>
    `;
  }).join("");

  qsa("[data-compare-toggle-run]").forEach((button) => {
    button.addEventListener("click", () => toggleRun(button.dataset.compareToggleRun));
  });
}

function renderSelectedTray() {
  const host = qs("#compare-selected-tray");
  if (!host) return;
  if (!compareState.selectedRuns.length) {
    host.innerHTML = `<div class="empty-state">Select completed runs from the list. The first selected run becomes baseline.</div>`;
    return;
  }

  host.innerHTML = compareState.selectedRuns.map((runId) => {
    const run = compareState.runs.find((item) => item.run_id === runId) || {};
    const isBaseline = compareState.baselineRunId === runId;
    const primary = run.primary_metric || {};
    return `
      <article class="compare-selected-card ${isBaseline ? "baseline" : ""}">
        <div class="compare-selected-card-head">
          <strong>${escapeHtml(runId)}</strong>
          <button type="button" class="icon-btn" data-compare-remove-run="${escapeHtml(runId)}" aria-label="Remove">&times;</button>
        </div>
        <span>${escapeHtml(run.model || "--")}</span>
        <b>${escapeHtml(primary.display_name || "Primary")}: ${primary.value == null ? "--" : Number(primary.value).toFixed(3)}</b>
        <button type="button" class="btn btn-sm ${isBaseline ? "btn-primary" : "btn-secondary"}" data-compare-baseline="${escapeHtml(runId)}">
          ${isBaseline ? "Baseline" : "Set Baseline"}
        </button>
      </article>
    `;
  }).join("");

  qsa("[data-compare-remove-run]").forEach((button) => {
    button.addEventListener("click", () => toggleRun(button.dataset.compareRemoveRun));
  });
  qsa("[data-compare-baseline]").forEach((button) => {
    button.addEventListener("click", () => setBaseline(button.dataset.compareBaseline));
  });
}

function renderDecisionSummary() {
  const host = qs("#compare-decision-summary");
  if (!host) return;
  const recommendation = compareState.result?.recommendation;
  const summary = compareState.result?.summary;
  if (!recommendation || !summary) {
    setText("#compare-recommendation-badge", "No comparison");
    host.innerHTML = compareState.architecture === "rnn"
      ? `
        <div class="rnn-compare-skeleton-grid">
          ${renderRnnMetricPlaceholder("Loss", "train/loss, val/loss")}
          ${renderRnnMetricPlaceholder("Classification", "Accuracy, Macro-F1")}
          ${renderRnnMetricPlaceholder("Regression", "MAE, RMSE, R2")}
          ${renderRnnMetricPlaceholder("Sequence", "Prediction curve, horizon error")}
        </div>
      `
      : `<div class="empty-state">Run comparison to see best model by metric, tradeoffs, and warnings.</div>`;
    return;
  }

  setText("#compare-recommendation-badge", recommendation.confidence ? `Confidence: ${recommendation.confidence}` : "Recommendation");
  const bestRows = Object.entries(summary.best_by_metric || {}).map(([key, item]) => `
    <tr>
      <td>${escapeHtml(metricDisplayName(key))}</td>
      <td>${escapeHtml(item.run_id || "--")}</td>
      <td>${item.value == null ? "--" : Number(item.value).toFixed(4)}</td>
    </tr>
  `).join("");

  host.innerHTML = `
    <div class="compare-recommendation">
      <span>Best overall</span>
      <strong>${escapeHtml(recommendation.best_overall || "--")}</strong>
      <p>${escapeHtml(recommendation.reason || "No recommendation available.")}</p>
    </div>
    <div class="compare-table-wrap">
      <table class="compare-table">
        <thead><tr><th>Metric</th><th>Best Run</th><th>Value</th></tr></thead>
        <tbody>${bestRows || `<tr><td colspan="3">No metric summary available.</td></tr>`}</tbody>
      </table>
    </div>
  `;
}

function renderChartTabs() {
  const host = qs("#compare-chart-tabs");
  if (!host) return;
  const keys = Object.keys(compareState.result?.series || {});
  if (!keys.length && compareState.architecture === "rnn") {
    host.innerHTML = ["Loss", "Accuracy", "Macro-F1", "MAE", "RMSE"].map((label) => `
      <button type="button" class="btn btn-sm btn-secondary" disabled>${escapeHtml(label)}</button>
    `).join("");
    return;
  }
  host.innerHTML = keys.slice(0, 8).map((key) => `
    <button type="button" class="btn btn-sm ${key === compareState.activeMetricKey ? "btn-primary" : "btn-secondary"}" data-compare-chart-key="${escapeHtml(key)}">
      ${escapeHtml(metricDisplayName(key))}
    </button>
  `).join("");
  qsa("[data-compare-chart-key]").forEach((button) => {
    button.addEventListener("click", () => {
      compareState.activeMetricKey = button.dataset.compareChartKey;
      renderModelComparePage();
    });
  });
}

function renderTrendChart() {
  const canvas = qs("#compare-trend-chart");
  const empty = qs("#compare-chart-empty");
  if (!canvas || typeof Chart === "undefined") return;
  const series = compareState.result?.series || {};
  const key = compareState.activeMetricKey || firstMetricKey(compareState.result);
  const metric = key ? series[key] : null;

  if (!metric || !Object.keys(metric.runs || {}).length) {
    empty?.classList.remove("hidden");
    if (empty) empty.textContent = compareState.architecture === "rnn"
      ? "Select 2 to 4 completed RNN runs and run comparison to view sequence metrics."
      : "Select 2 to 4 completed CNN runs and run comparison.";
    if (trendChart) {
      trendChart.destroy();
      trendChart = null;
    }
    return;
  }
  empty?.classList.add("hidden");

  const palette = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7"];
  const datasets = Object.entries(metric.runs).map(([runId, item], index) => ({
    label: runId,
    data: (item.x || []).map((x, idx) => ({ x, y: (item.y || [])[idx] })),
    borderColor: palette[index % palette.length],
    backgroundColor: palette[index % palette.length],
    tension: 0.25,
    pointRadius: 2,
    borderWidth: 2,
  }));

  if (trendChart) trendChart.destroy();
  trendChart = new Chart(canvas, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      plugins: {
        legend: { labels: { color: getComputedStyle(document.body).getPropertyValue("--text") || "#e5e7eb" } },
        tooltip: { mode: "nearest", intersect: false },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Epoch" },
          grid: { color: "rgba(148, 163, 184, 0.14)" },
        },
        y: {
          title: { display: true, text: metric.display_name || key },
          grid: { color: "rgba(148, 163, 184, 0.14)" },
        },
      },
    },
  });
}

function renderOutputComparison() {
  const empty = qs("#compare-output-empty");
  const host = qs("#compare-output-results");
  if (!empty || !host) return;
  if (compareState.architecture === "rnn") {
    empty.classList.remove("hidden");
    empty.textContent = "Sequence output comparison is not enabled in Phase 3E. This phase compares completed RNN training metrics only.";
    host.innerHTML = `
      <div class="rnn-compare-skeleton-grid">
        ${renderRnnMetricPlaceholder("Ground truth", "target column / label sequence")}
        ${renderRnnMetricPlaceholder("Prediction", "LSTM / GRU output sequence")}
        ${renderRnnMetricPlaceholder("Diagnostics", "delay, residual, transition stability")}
      </div>
    `;
    return;
  }

  if (compareState.outputComparing) {
    empty.classList.remove("hidden");
    empty.textContent = "Running output comparison. This may take a moment while each model performs inference.";
    host.innerHTML = "";
    return;
  }

  const result = compareState.outputResult;
  if (!result || !Array.isArray(result.outputs) || !result.outputs.length) {
    empty.classList.remove("hidden");
    empty.textContent = "Select 2 to 4 runs and upload one test image to compare prediction overlays.";
    host.innerHTML = "";
    return;
  }

  empty.classList.add("hidden");
  host.innerHTML = result.outputs.map((output) => {
    const summary = output.summary || {};
    const annotatedUrl = output.urls?.annotated_image || "";
    const labels = Array.isArray(summary.detected_classes) && summary.detected_classes.length
      ? summary.detected_classes.join(", ")
      : "--";
    return `
      <article class="compare-output-card">
        <div class="compare-output-head">
          <div>
            <strong>${escapeHtml(output.run_id || "--")}</strong>
            <span>${escapeHtml(output.weight_type || "--")}.pt · ${escapeHtml(output.model_name || "--")}</span>
          </div>
          <span class="summary-badge badge-neutral">${escapeHtml(summary.inference_time_ms ?? "--")} ms</span>
        </div>
        <div class="compare-output-image">
          ${annotatedUrl ? `<img src="${escapeHtml(annotatedUrl)}?t=${Date.now()}" alt="Prediction overlay for ${escapeHtml(output.run_id || "run")}">` : `<div class="empty-state">No overlay image returned.</div>`}
        </div>
        <div class="compare-output-stats">
          <div><span>Predictions</span><strong>${escapeHtml(summary.prediction_count ?? "--")}</strong></div>
          <div><span>Avg confidence</span><strong>${summary.average_confidence == null ? "--" : Number(summary.average_confidence).toFixed(3)}</strong></div>
          <div><span>Mask area</span><strong>${summary.mask_area_ratio == null ? "--" : Number(summary.mask_area_ratio).toFixed(3)}</strong></div>
          <div><span>Classes</span><strong>${escapeHtml(labels)}</strong></div>
        </div>
      </article>
    `;
  }).join("");
}

function renderConfigDiff() {
  const host = qs("#compare-config-diff");
  if (!host) return;
  const diff = compareState.result?.summary?.config_diff || {};
  const selected = compareState.result?.selected_runs || [];
  if (!compareState.result) {
    host.innerHTML = `<div class="empty-state">Config differences appear after comparison.</div>`;
    return;
  }
  const keys = Object.keys(diff);
  if (!keys.length) {
    host.innerHTML = `<div class="empty-state">Selected runs have no visible config differences in tracked fields.</div>`;
    return;
  }
  host.innerHTML = `
    <div class="compare-table-wrap">
      <table class="compare-table">
        <thead>
          <tr><th>Config</th>${selected.map((run) => `<th>${escapeHtml(run.run_id)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${keys.map((key) => `
            <tr>
              <td>${escapeHtml(key)}</td>
              ${selected.map((run) => `<td>${escapeHtml(diff[key]?.[run.run_id] ?? "--")}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderCompareReport() {
  const host = qs("#compare-report-files");
  if (!host) return;
  const badge = qs("#compare-report-badge");
  if (badge) {
    badge.textContent = compareState.reportExporting
      ? "Exporting"
      : compareState.reportResult?.report_id
        ? compareState.reportResult.report_id
        : "Not exported";
  }
  if (compareState.reportExporting) {
    host.innerHTML = `<div class="empty-state">Exporting compare report...</div>`;
    return;
  }
  const latestFiles = compareState.reportResult?.files || [];
  const latestHtml = latestFiles.length
    ? `
      <div class="compare-report-group">
        <h3>Latest Export</h3>
        ${latestFiles.map(renderReportFileRow).join("")}
      </div>
    `
    : `<div class="empty-state">Export a report after comparison to download JSON, Markdown, CSV, and PDF files.</div>`;
  const reports = compareState.reportHistory || [];
  const historyHtml = compareState.reportLoading
    ? `<div class="empty-state">Loading report history...</div>`
    : reports.length
      ? `
        <div class="compare-report-group">
          <h3>Report History</h3>
          ${reports.map((report) => `
            <article class="compare-report-history-card">
              <div>
                <strong>${escapeHtml(report.report_id || "--")}</strong>
                <span>${escapeHtml(report.architecture || "--")} · ${escapeHtml(report.task_family || "--")} · ${escapeHtml((report.selected_run_ids || []).join(", ") || "--")}</span>
                <small>${escapeHtml(report.recommendation?.best_overall ? `Best: ${report.recommendation.best_overall}` : "No recommendation")}</small>
              </div>
              <div class="inline-actions">
                ${(report.files || []).map(renderReportFileButton).join("")}
                <button type="button" class="btn btn-secondary btn-sm" data-compare-report-delete="${escapeHtml(report.report_id || "")}">
                  <i class="fa-solid fa-trash"></i> Delete
                </button>
              </div>
            </article>
          `).join("")}
        </div>
      `
      : `<div class="empty-state">No compare reports have been exported for this project.</div>`;
  host.innerHTML = `${latestHtml}${historyHtml}`;
  qsa("[data-compare-report-download]").forEach((button) => {
    button.addEventListener("click", () => downloadCompareReportFile(button.dataset.compareReportDownload, button.dataset.compareReportFilename));
  });
  qsa("[data-compare-report-delete]").forEach((button) => {
    button.addEventListener("click", () => deleteCompareReport(button.dataset.compareReportDelete));
  });
}

function updateCompareActions() {
  const button = qs("#btn-run-compare");
  const outputButton = qs("#btn-run-output-compare");
  const reportButton = qs("#btn-export-compare-report");
  const isRnn = compareState.architecture === "rnn";
  const enabled = appState.currentProjectId
    && compareState.selectedRuns.length >= 2
    && compareState.selectedRuns.length <= 4
    && !compareState.comparing;
  if (button) {
    button.disabled = !enabled;
    button.innerHTML = compareState.comparing
      ? `<i class="fa-solid fa-spinner fa-spin"></i> Comparing`
      : `<i class="fa-solid fa-chart-line"></i> Compare Selected`;
  }

  if (outputButton) {
    const hasFile = Boolean(qs("#compare-output-image-file")?.files?.[0]);
    const outputEnabled = enabled && !isRnn && hasFile && !compareState.outputComparing;
    outputButton.disabled = !outputEnabled;
    outputButton.innerHTML = compareState.outputComparing
      ? `<i class="fa-solid fa-spinner fa-spin"></i> Comparing Outputs`
      : `<i class="fa-solid fa-images"></i> Compare Outputs`;
  }
  if (reportButton) {
    const reportEnabled = Boolean(appState.currentProjectId && compareState.result && !compareState.reportExporting);
    reportButton.disabled = !reportEnabled;
    reportButton.innerHTML = compareState.reportExporting
      ? `<i class="fa-solid fa-spinner fa-spin"></i> Exporting`
      : `<i class="fa-solid fa-file-arrow-down"></i> Export Report`;
  }
  qsa("#compare-output-image-file, #compare-output-conf, #compare-output-iou, #compare-output-imgsz, #compare-output-device").forEach((control) => {
    control.disabled = isRnn;
  });
}

async function downloadCompareReportFile(url, filename) {
  if (!url) return;
  try {
    const headers = {};
    if (appState.bootstrap?.token) headers["X-VTS-Token"] = appState.bootstrap.token;
    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new Error(await response.text() || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = filename || "compare_report";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(downloadUrl);
  } catch (err) {
    eventBus.emit("toast", `Download report failed: ${err.message}`);
  }
}

function renderReportFileRow(file) {
  return `
    <div class="compare-report-file">
      <div>
        <strong>${escapeHtml(file.filename || "--")}</strong>
        <span>${escapeHtml(formatBytes(file.size_bytes))}</span>
      </div>
      ${renderReportFileButton(file)}
    </div>
  `;
}

function renderReportFileButton(file) {
  return `
    <button type="button" class="btn btn-secondary btn-sm" data-compare-report-download="${escapeHtml(file.url || "")}" data-compare-report-filename="${escapeHtml(file.filename || "report")}" ${file.url ? "" : "disabled"}>
      <i class="fa-solid fa-download"></i> ${escapeHtml(file.filename || "Download")}
    </button>
  `;
}

function renderRnnMetricPlaceholder(title, body) {
  return `
    <article class="rnn-compare-placeholder-card">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(body)}</span>
      <em>Schema placeholder</em>
    </article>
  `;
}

function firstMetricKey(payload) {
  const keys = Object.keys(payload?.series || {});
  return keys[0] || null;
}

function metricDisplayName(key) {
  const metric = compareState.result?.series?.[key];
  if (metric?.display_name) return metric.display_name;
  if (key.includes("mAP50-95")) return "mAP50-95";
  if (key.includes("mAP50")) return "mAP50";
  return key.split("/").pop().replaceAll("_", " ");
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (!Number.isFinite(bytes) || bytes <= 0) return "--";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
