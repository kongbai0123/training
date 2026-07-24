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
  renderSplitClassDistribution(project.split_report || null, images, eligible);
}

function renderSplitReportUI(report) {
  if (!report) return;
  setHTML("#split-report-card", `
    <div class="status-guard ${report.score >= 80 ? "success" : report.score >= 50 ? "warning" : "danger"}">
      <div class="guard-title">${escapeHtml(t("split.report.score", { score: report.score ?? "--" }))}</div>
      <ul>${(report.warnings || [t("split.report.noWarnings")]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
  `);
  const project = appState.currentProject || {};
  const images = Array.isArray(project.images) ? project.images : [];
  renderSplitClassDistribution(report, images, images.length);
}

function renderSplitClassDistribution(report, images, eligible) {
  const project = appState.currentProject || {};
  const classNames = Array.isArray(project.class_names) ? project.class_names : [];
  const splitNames = ["train", "val", "test"];
  const ratios = Object.fromEntries(splitNames.map((key) => [
    key,
    (Number(qs(`#input-ratio-${key}`)?.value) || 0) / 100
  ]));
  const isActual = !!report?.class_distribution && !!report?.split_counts;
  const splitCounts = isActual
    ? Object.fromEntries(splitNames.map((key) => [key, Number(report.split_counts?.[key] || 0)]))
    : allocateIntegerCounts(eligible, ratios);
  const classDistribution = isActual
    ? report.class_distribution
    : estimateClassDistribution(images, classNames, ratios);

  const mode = qs("#split-distribution-mode");
  if (mode) {
    mode.className = `badge ${isActual ? "badge-success" : "badge-muted"}`;
    mode.textContent = t(isActual ? "split.distribution.actual" : "split.distribution.estimated");
  }

  setHTML("#split-set-counts", splitNames.map((key) => `
    <article class="split-set-count split-set-count-${key}">
      <span>${escapeHtml(t(`split.${key}`))}</span>
      <strong>${escapeHtml(splitCounts[key] || 0)}</strong>
      <small>${escapeHtml(t("split.imagesUnit"))}</small>
    </article>
  `).join(""));

  if (classNames.length === 0) {
    setHTML("#split-class-distribution", `
      <tr><td colspan="5" class="split-class-empty">${escapeHtml(t("split.classDistributionEmpty"))}</td></tr>
    `);
    return;
  }

  const rows = classNames.map((className) => {
    const counts = Object.fromEntries(splitNames.map((key) => [
      key,
      Number(classDistribution?.[key]?.[className] || 0)
    ]));
    const total = splitNames.reduce((sum, key) => sum + counts[key], 0);
    return `
      <tr>
        <th scope="row"><span class="split-class-name">${escapeHtml(className)}</span></th>
        ${splitNames.map((key) => `
          <td>
            <div class="split-class-count-cell">
              <strong>${escapeHtml(counts[key])}</strong>
              <span><i style="width:${total > 0 ? Math.min(100, counts[key] / total * 100) : 0}%"></i></span>
            </div>
          </td>
        `).join("")}
        <td><strong>${escapeHtml(total)}</strong></td>
      </tr>
    `;
  });
  setHTML("#split-class-distribution", rows.join(""));
}

function estimateClassDistribution(images, classNames, ratios) {
  const totals = Object.fromEntries(classNames.map((className) => [className, 0]));
  images.forEach((image) => {
    (image?.annotations || []).forEach((annotation) => {
      const className = annotation?.category;
      if (className in totals) totals[className] += 1;
    });
    const imageClass = image?.class_name || image?.category;
    if (imageClass in totals) totals[imageClass] += 1;
  });
  const distribution = { train: {}, val: {}, test: {} };
  classNames.forEach((className) => {
    const allocated = allocateIntegerCounts(totals[className], ratios);
    ["train", "val", "test"].forEach((key) => {
      distribution[key][className] = allocated[key];
    });
  });
  return distribution;
}

function allocateIntegerCounts(total, ratios) {
  const keys = ["train", "val", "test"];
  const safeTotal = Math.max(0, Math.floor(Number(total) || 0));
  const exact = Object.fromEntries(keys.map((key) => [key, safeTotal * Math.max(0, Number(ratios[key]) || 0)]));
  const result = Object.fromEntries(keys.map((key) => [key, Math.floor(exact[key])]));
  let remaining = safeTotal - keys.reduce((sum, key) => sum + result[key], 0);
  keys
    .slice()
    .sort((a, b) => (exact[b] - result[b]) - (exact[a] - result[a]))
    .forEach((key) => {
      if (remaining <= 0) return;
      result[key] += 1;
      remaining -= 1;
    });
  return result;
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
