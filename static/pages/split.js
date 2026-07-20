import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { apiFetch } from "../api.js";
import { followServerTask } from "../core/task_progress.js";
import { qs, setText, setHTML, escapeHtml } from "../utils.js";

let isBalancingSplitRatios = false;

export function initSplit() {
  ["train", "val", "test"].forEach((key) => {
    qs(`#input-ratio-${key}`)?.addEventListener("input", () => { rebalanceSplitRatios(key); renderSplitPreview(); });
    qs(`#input-ratio-${key}`)?.addEventListener("change", () => { rebalanceSplitRatios(key); renderSplitPreview(); });
  });
  qs("#split-method")?.addEventListener("change", renderSplitPreview);
  updateSplitRatioTotal();
  renderSplitPreview();

  qs("#form-split-dataset")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    updateSplitRatioTotal();
    const train = Number(qs("#input-ratio-train").value) / 100;
    const val = Number(qs("#input-ratio-val").value) / 100;
    const test = Number(qs("#input-ratio-test").value) / 100;
    if (Math.abs(train + val + test - 1) > 0.01) {
      eventBus.emit("toast", t("split.toast.ratio"));
      return;
    }
    try {
      const started = await apiFetch(`/api/projects/${appState.currentProjectId}/split/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          method: qs("#split-method").value,
          ratio: { train, val, test }
        })
      });
      const data = await followServerTask(started.job_id, {
        kind: "sync",
        title: t("split.progress.title"),
        button: event.submitter,
      });
      renderSplitReportUI(data.report);
      eventBus.emit("toast", t("split.toast.done"));
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", t("split.toast.failed", { message: err.message }));
    }
  });
}

export function renderSplitPage(status) {
  renderSplitPreview();
  if (appState.currentProject?.split_report) {
    renderSplitReportUI(appState.currentProject.split_report);
  } else if (!status.splitComplete) {
    setHTML("#split-report-card", "");
  }
}

function renderSplitPreview() {
  const project = appState.currentProject || {};
  const images = Array.isArray(project.images) ? project.images : [];
  const total = images.length || Number(project.image_count || project.dataset_count || 0);
  const annotated = images.length
    ? images.filter((item) => item?.annotated || item?.annotation_path || item?.json_path).length
    : Number(project.annotated_count || 0);
  const eligible = annotated || total;
  const ratios = [
    ["train", Number(qs("#input-ratio-train")?.value) || 0],
    ["val", Number(qs("#input-ratio-val")?.value) || 0],
    ["test", Number(qs("#input-ratio-test")?.value) || 0]
  ];
  setHTML("#split-distribution-preview", ratios.map(([key, ratio]) => `
    <div class="split-distribution-row">
      <strong>${escapeHtml(t(`split.${key}`))}</strong>
      <div class="split-distribution-track"><div class="split-distribution-fill" style="width:${Math.min(100, ratio)}%"></div></div>
      <span class="split-distribution-value">${ratio}% · ${Math.round(eligible * ratio / 100)}</span>
    </div>
  `).join(""));
  const excluded = Math.max(0, total - eligible);
  const method = qs("#split-method")?.value || "stratified";
  setHTML("#split-readiness-summary", `
    <div class="split-readiness-item"><span>${escapeHtml(t("split.eligible"))}</span><strong>${eligible}</strong></div>
    <div class="split-readiness-item"><span>${escapeHtml(t("split.excluded"))}</span><strong>${excluded}</strong></div>
    <div class="split-readiness-item"><span>${escapeHtml(t("split.leakageControl"))}</span><strong>${escapeHtml(t(`split.risk.${method}`))}</strong></div>
  `);
}

function renderSplitReportUI(report) {
  if (!report) return;
  setHTML("#split-report-card", `
    <div class="status-guard ${report.score >= 80 ? "success" : report.score >= 50 ? "warning" : "danger"}">
      <div class="guard-title">${escapeHtml(t("split.report.score", { score: report.score ?? "--" }))}</div>
      <ul>${(report.warnings || [t("split.report.noWarnings")]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
  `);
}

function rebalanceSplitRatios(changedKey) {
  if (isBalancingSplitRatios) return;
  const keys = ["train", "val", "test"];
  const mins = { train: 10, val: 5, test: 5 };
  const fields = Object.fromEntries(keys.map((key) => [key, qs(`#input-ratio-${key}`)]));
  if (!fields[changedKey]) return;

  isBalancingSplitRatios = true;
  const others = keys.filter((key) => key !== changedKey);
  const changedMax = 100 - mins[others[0]] - mins[others[1]];
  const changedValue = clampNumber(Number(fields[changedKey].value), mins[changedKey], changedMax);
  const remaining = 100 - changedValue;
  const firstCurrent = Math.max(0, Number(fields[others[0]].value) || 0);
  const secondCurrent = Math.max(0, Number(fields[others[1]].value) || 0);
  const otherTotal = firstCurrent + secondCurrent;
  const firstRatio = otherTotal > 0 ? firstCurrent / otherTotal : 0.5;

  let firstValue = Math.round(remaining * firstRatio);
  let secondValue = remaining - firstValue;

  if (firstValue < mins[others[0]]) {
    firstValue = mins[others[0]];
    secondValue = remaining - firstValue;
  }
  if (secondValue < mins[others[1]]) {
    secondValue = mins[others[1]];
    firstValue = remaining - secondValue;
  }

  fields[changedKey].value = String(Math.round(changedValue));
  fields[others[0]].value = String(Math.round(firstValue));
  fields[others[1]].value = String(100 - Number(fields[changedKey].value) - Number(fields[others[0]].value));
  updateSplitRatioTotal();
  isBalancingSplitRatios = false;
}

function updateSplitRatioTotal() {
  const totalEl = qs("#split-ratio-total");
  if (!totalEl) return;
  const total = ["train", "val", "test"].reduce((sum, key) => {
    return sum + (Number(qs(`#input-ratio-${key}`)?.value) || 0);
  }, 0);
  totalEl.textContent = `${total}%`;
  totalEl.classList.toggle("is-valid", total === 100);
  totalEl.classList.toggle("is-invalid", total !== 100);
}

function clampNumber(value, min, max) {
  const normalized = Number.isFinite(value) ? value : min;
  return Math.min(max, Math.max(min, normalized));
}
