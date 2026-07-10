import { t } from "../state.js";
import { escapeHtml } from "../utils.js";

const RNN_TASK_TOKENS = ["sequence", "time_series", "timeseries", "rnn"];

export function resolveDashboardProjectMode(project) {
  if (!project) return null;
  const taskType = String(project.task_type || "").toLowerCase();
  if (RNN_TASK_TOKENS.some((token) => taskType.includes(token))) return "rnn";

  const files = project.file_summary || {};
  const hasSequenceData = Boolean(
    files.sequence_manifest
    || Number(files.sequence_csv_files || 0) > 0
    || Number(files.sequence_files || 0) > 0
  );
  const hasImageData = Number(files.images || 0) > 0 || Array.isArray(project.images) && project.images.length > 0;
  return hasSequenceData && !hasImageData ? "rnn" : "cnn";
}

export function buildProjectStatusView({ status = {}, project = null, models = [], rnnState = {} } = {}) {
  if (!project) {
    return {
      hasProject: false,
      mode: null,
      phases: [],
      readyCount: 0,
      attentionCount: 0,
    };
  }

  const mode = resolveDashboardProjectMode(project);
  const phases = mode === "rnn"
    ? buildRnnPhases({ status, project, models, rnnState })
    : buildCnnPhases({ status, project, models });

  return {
    hasProject: true,
    mode,
    phases,
    readyCount: phases.filter((phase) => phase.state === "ready").length,
    attentionCount: phases.filter((phase) => phase.state === "attention").length,
  };
}

export function renderProjectStatusStrip(view) {
  if (!view?.hasProject) {
    return `
      <section class="project-status-strip project-status-empty" data-ui-smoke="project-status-strip">
        <div>
          <h2><i class="fa-solid fa-gauge-high"></i> ${escapeHtml(t("dashboard.status.title"))}</h2>
          <p>${escapeHtml(t("dashboard.status.empty"))}</p>
        </div>
        <button type="button" class="btn btn-primary btn-sm" data-nav="projects">
          <i class="fa-solid fa-folder-plus"></i> ${escapeHtml(t("dashboard.status.action.openProject"))}
        </button>
      </section>
    `;
  }

  return `
    <section class="project-status-strip" data-status-mode="${escapeHtml(view.mode)}" data-ui-smoke="project-status-strip" aria-label="${escapeHtml(t("dashboard.status.aria"))}">
      <header class="project-status-heading">
        <div>
          <h2><i class="fa-solid fa-gauge-high"></i> ${escapeHtml(t("dashboard.status.title"))}</h2>
          <p>${escapeHtml(t(`dashboard.status.subtitle.${view.mode}`))}</p>
        </div>
        <div class="project-status-summary" aria-label="${escapeHtml(t("dashboard.status.summaryAria"))}">
          <strong>${escapeHtml(t("dashboard.status.readySummary", { ready: view.readyCount, total: view.phases.length }))}</strong>
          ${view.attentionCount ? `<span>${escapeHtml(t("dashboard.status.attentionSummary", { count: view.attentionCount }))}</span>` : ""}
        </div>
      </header>
      <div class="project-status-phases">
        ${view.phases.map(renderStatusPhase).join("")}
      </div>
    </section>
  `;
}

function buildCnnPhases({ status, project, models }) {
  const runs = normalizedRuns(project);
  const completedRuns = runs.filter(isCompletedRun);
  const fileSummary = project.file_summary || {};
  const imageCount = Number(status.imageCount || fileSummary.images || 0);
  const classCount = Array.isArray(status.classNames) ? status.classNames.length : Array.isArray(project.class_names) ? project.class_names.length : 0;
  const annotated = Number(status.annotatedCount || project.annotation_progress?.annotated || 0);
  const coverage = imageCount ? Math.round((annotated / imageCount) * 100) : 0;
  const pendingDrafts = Number(status.autoLabelReviewGate?.pending || project.auto_label_review_gate?.pending || 0);
  const exportCount = countExports(project);
  const modelCount = countModels(models, fileSummary);
  const hasModel = Boolean(status.bestModelExists || modelCount > 0 || completedRuns.length > 0);
  const bestMetric = findBestMetric([...models, ...completedRuns], [
    ["best_map50_95_m", "mAP50-95"],
    ["map50_95", "mAP50-95"],
    ["metrics/mAP50-95(M)", "mAP50-95"],
    ["best_map50_m", "mAP50"],
    ["map50", "mAP50"],
  ]);

  const dataReady = imageCount > 0 && classCount > 0;
  const annotationReady = coverage >= 95 && pendingDrafts === 0;
  const trainingActive = runs.length > 0 || Boolean(status.trainReady);

  return [
    phase({
      icon: "fa-images",
      titleKey: "dashboard.status.phase.cnn.data",
      state: dataReady ? "ready" : imageCount > 0 ? "attention" : "waiting",
      metrics: [
        metric("dashboard.status.metric.images", imageCount),
        metric("dashboard.status.metric.classes", classCount),
        metric("dashboard.status.metric.quality", project.dataset_health ? t("common.done") : t("common.notRun")),
      ],
      actionKey: "dashboard.status.action.manageData",
      page: "dataset",
    }),
    phase({
      icon: "fa-pen-nib",
      titleKey: "dashboard.status.phase.cnn.annotation",
      state: annotationReady ? "ready" : dataReady ? "attention" : "waiting",
      metrics: [
        metric("dashboard.status.metric.annotated", `${annotated}/${imageCount}`),
        metric("dashboard.status.metric.coverage", `${coverage}%`),
        metric("dashboard.status.metric.pendingDrafts", pendingDrafts),
      ],
      actionKey: pendingDrafts ? "dashboard.status.action.reviewDrafts" : "dashboard.status.action.openLabelMe",
      page: pendingDrafts ? "auto-labeling" : "labelme",
    }),
    phase({
      icon: "fa-microchip",
      titleKey: "dashboard.status.phase.cnn.training",
      state: hasModel ? "ready" : trainingActive ? "active" : dataReady ? "attention" : "waiting",
      metrics: [
        metric("dashboard.status.metric.split", splitValue(status)),
        metric("dashboard.status.metric.runs", runs.length),
        metric("dashboard.status.metric.bestScore", bestMetric || "--"),
      ],
      actionKey: hasModel ? "dashboard.status.action.evaluate" : "dashboard.status.action.training",
      page: hasModel ? "evaluation" : "training",
    }),
    phase({
      icon: "fa-box-archive",
      titleKey: "dashboard.status.phase.cnn.delivery",
      state: exportCount > 0 ? "ready" : hasModel ? "active" : "waiting",
      metrics: [
        metric("dashboard.status.metric.models", modelCount),
        metric("dashboard.status.metric.exports", exportCount),
        metric("dashboard.status.metric.artifact", latestArtifact(project) || "--", true),
      ],
      actionKey: "dashboard.status.action.export",
      page: "export",
    }),
  ];
}

function buildRnnPhases({ project, models, rnnState }) {
  const runs = normalizedRuns(project);
  const completedRuns = runs.filter(isCompletedRun);
  const files = project.file_summary || {};
  const readiness = rnnState.readiness || {};
  const csv = readiness.summary?.csv || {};
  const config = rnnState.config || project.rnn_config || readiness.summary?.active_config || {};
  const csvCount = Number(csv.file_count || files.sequence_csv_files || 0);
  const sequenceCount = Number(csv.sequence_count || project.sequence_manifest?.sequence_count || 0);
  const featureCount = Number(csv.feature_dim || config.feature_dim || (Array.isArray(config.feature_columns) ? config.feature_columns.length : 0));
  const target = String(config.target_column || "").trim();
  const windowSize = Number(config.sequence_length || config.window_size || readiness.sequence_length || 0);
  const exportCount = countExports(project);
  const modelCount = countModels(models, files);
  const hasModel = Boolean(modelCount > 0 || completedRuns.length > 0);
  const taskHead = String(config.task_head || project.task_type || "").toLowerCase();
  const isRegression = taskHead.includes("regression");
  const bestMetric = findBestMetric([...models, ...completedRuns], isRegression ? [
    ["rmse", "RMSE"],
    ["val/rmse", "RMSE"],
    ["val_rmse", "RMSE"],
    ["mae", "MAE"],
    ["val/mae", "MAE"],
  ] : [
    ["macro_f1", "Macro-F1"],
    ["val/macro_f1", "Macro-F1"],
    ["accuracy", "Accuracy"],
    ["val/accuracy", "Accuracy"],
  ]);

  const dataReady = csvCount > 0;
  const schemaReady = dataReady && featureCount > 0 && Boolean(target);
  const trainingActive = runs.length > 0 || schemaReady;

  return [
    phase({
      icon: "fa-file-csv",
      titleKey: "dashboard.status.phase.rnn.data",
      state: dataReady ? "ready" : "waiting",
      metrics: [
        metric("dashboard.status.metric.csvFiles", csvCount),
        metric("dashboard.status.metric.sequences", sequenceCount || "--"),
        metric("dashboard.status.metric.quality", readiness.ready ? t("common.ready") : dataReady ? t("common.notRun") : "--"),
      ],
      actionKey: "dashboard.status.action.sequenceData",
      rnnPanel: "sequence-dataset",
    }),
    phase({
      icon: "fa-table-columns",
      titleKey: "dashboard.status.phase.rnn.schema",
      state: schemaReady ? "ready" : dataReady ? "attention" : "waiting",
      metrics: [
        metric("dashboard.status.metric.features", featureCount || "--"),
        metric("dashboard.status.metric.target", target || t("dashboard.status.value.notSet"), true),
        metric("dashboard.status.metric.window", windowSize || t("dashboard.status.value.notSet")),
      ],
      actionKey: "dashboard.status.action.configureSchema",
      rnnPanel: "features-labels",
    }),
    phase({
      icon: "fa-chart-line",
      titleKey: "dashboard.status.phase.rnn.training",
      state: hasModel ? "ready" : trainingActive ? "active" : "waiting",
      metrics: [
        metric("dashboard.status.metric.runs", runs.length),
        metric("dashboard.status.metric.task", readableTask(config.task_head || project.task_type)),
        metric("dashboard.status.metric.bestScore", bestMetric || "--"),
      ],
      actionKey: hasModel ? "dashboard.status.action.evaluate" : "dashboard.status.action.training",
      rnnPanel: hasModel ? "evaluation" : "training",
    }),
    phase({
      icon: "fa-box-archive",
      titleKey: "dashboard.status.phase.rnn.delivery",
      state: exportCount > 0 ? "ready" : hasModel ? "active" : "waiting",
      metrics: [
        metric("dashboard.status.metric.models", modelCount),
        metric("dashboard.status.metric.exports", exportCount),
        metric("dashboard.status.metric.contract", exportCount > 0 ? t("dashboard.status.value.included") : "--"),
      ],
      actionKey: "dashboard.status.action.export",
      rnnPanel: "export",
    }),
  ];
}

function phase(config) {
  return config;
}

function metric(labelKey, value, truncate = false) {
  return { labelKey, value: value === null || value === undefined || value === "" ? "--" : String(value), truncate };
}

function renderStatusPhase(item) {
  const actionAttributes = item.rnnPanel
    ? `data-rnn-target="${escapeHtml(item.rnnPanel)}"`
    : `data-nav="${escapeHtml(item.page)}"`;
  return `
    <article class="project-status-phase status-${escapeHtml(item.state)}">
      <header>
        <span class="project-status-phase-icon"><i class="fa-solid ${escapeHtml(item.icon)}"></i></span>
        <h3>${escapeHtml(t(item.titleKey))}</h3>
        <span class="project-status-state">${escapeHtml(t(`dashboard.status.state.${item.state}`))}</span>
      </header>
      <dl>
        ${item.metrics.map((entry) => `
          <div>
            <dt>${escapeHtml(t(entry.labelKey))}</dt>
            <dd class="${entry.truncate ? "is-truncated" : ""}" title="${escapeHtml(entry.value)}">${escapeHtml(entry.value)}</dd>
          </div>
        `).join("")}
      </dl>
      <button type="button" class="project-status-action" ${actionAttributes}>
        <span>${escapeHtml(t(item.actionKey))}</span>
        <i class="fa-solid fa-arrow-right" aria-hidden="true"></i>
      </button>
    </article>
  `;
}

function normalizedRuns(project) {
  return Array.isArray(project.training_runs) ? project.training_runs : [];
}

function isCompletedRun(run) {
  return String(run?.status || "").toLowerCase() === "completed";
}

function countModels(models, fileSummary) {
  if (Array.isArray(models) && models.length) return models.length;
  return Number(fileSummary.best_weights || 0) + Number(fileSummary.last_weights || 0);
}

function countExports(project) {
  const fileCount = Number(project.file_summary?.exports || 0);
  if (fileCount) return fileCount;
  return Array.isArray(project.exports) ? project.exports.length : 0;
}

function latestArtifact(project) {
  const exports = Array.isArray(project.exports) ? project.exports : [];
  const latest = exports.length ? exports[exports.length - 1] : project.latest_export;
  if (!latest) return "";
  if (typeof latest === "string") return latest;
  return latest.filename || latest.artifact_type || latest.export_id || latest.kind || "";
}

function splitValue(status) {
  if (!status.splitComplete) return t("common.notReady");
  const counts = status.splitCounts || {};
  return `${Number(counts.train || 0)} / ${Number(counts.val || 0)} / ${Number(counts.test || 0)}`;
}

function findBestMetric(items, candidates) {
  for (const item of items) {
    for (const [key, label] of candidates) {
      const value = metricValue(item, key);
      if (Number.isFinite(value)) return `${label} ${formatMetric(value)}`;
    }
  }
  return "";
}

function metricValue(item, key) {
  const sources = [item, item?.metrics, item?.summary, item?.summary?.metrics, item?.final_metrics, item?.best_metrics];
  for (const source of sources) {
    if (!source || typeof source !== "object") continue;
    const value = Number(source[key]);
    if (Number.isFinite(value)) return value;
  }
  return NaN;
}

function formatMetric(value) {
  if (Math.abs(value) >= 100) return value.toFixed(1);
  if (Math.abs(value) >= 10) return value.toFixed(2);
  return value.toFixed(3);
}

function readableTask(value) {
  const task = String(value || "").replace(/^sequence_/, "").replace(/_/g, " ").trim();
  if (!task) return "--";
  return task.replace(/\b\w/g, (letter) => letter.toUpperCase());
}
