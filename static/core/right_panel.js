import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { qs, setHTML, escapeHtml } from "../utils.js";
import { trainingModeState, isRnnTrainingWorkspaceActive } from "../pages/training_modes.js?v=20260721-rnn-evaluation-sync";
import { followServerTask } from "./task_progress.js";

function contextCardFor(selector) {
  return qs(selector)?.closest(".workspace-context-card, .summary-section") || null;
}

function setContextCardVisible(selector, visible) {
  const card = contextCardFor(selector);
  if (card) card.style.display = visible ? "" : "none";
}

function setWorkspaceContextExpanded(expanded) {
  const panel = qs("#workspace-context-panel");
  const strip = qs("#workspace-context-strip");
  const toggle = qs("#workspace-context-toggle");
  if (!panel || !strip || !toggle) return;
  panel.classList.toggle("is-collapsed", !expanded);
  strip.hidden = !expanded;
  toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
}

export function initWorkspaceContextPanel() {
  const toggle = qs("#workspace-context-toggle");
  if (toggle) {
    const stored = localStorage.getItem("vts.workspaceContextExpanded");
    setWorkspaceContextExpanded(stored === "true");
    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") !== "true";
      localStorage.setItem("vts.workspaceContextExpanded", expanded ? "true" : "false");
      setWorkspaceContextExpanded(expanded);
    });
  }
  qs("#btn-project-assistant-sync-context")?.addEventListener("click", syncProjectAssistantContextArtifacts);
}

async function syncProjectAssistantContextArtifacts() {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", t("projectAssistant.toast.noActiveProject"));
    return;
  }
  const button = qs("#btn-project-assistant-sync-context");
  if (button) button.disabled = true;
  try {
    const started = await apiFetch(`/api/project-assistant/projects/${encodeURIComponent(appState.currentProjectId)}/sync-artifacts/jobs`, {
      method: "POST",
    });
    const result = await followServerTask(started.job_id, {
      kind: "sync",
      title: t("task.sync.title"),
      button,
    });
    eventBus.emit("toast", t("projectAssistant.toast.syncedArtifacts", {
      count: result.document_count || 0,
      chunks: result.chunk_count || 0,
    }));
  } finally {
    if (button) button.disabled = false;
  }
}

function updateWorkspaceContextSummary(pageId, status, config = {}) {
  const projectLabel = status.hasProject ? status.projectName : t("common.noProject");
  const pageLabel = config.title || getPageTitle(pageId);
  const actionsCount = config.suppressActions ? 0 : (config.actions || []).length;
  const warningCount = config.suppressWarnings ? 0 : ((config.warnings || []).length);
  const notesCount = config.suppressWarnings ? 0 : ((config.notes || []).length);
  const readiness = status.hasProject
    ? (status.trainReady ? t("workspace.trainingReady") : status.hasDataset ? t("workspace.datasetActive") : t("workspace.projectOpen"))
    : t("workspace.idle");
  setHTML("#workspace-context-summary", `
    <span class="summary-badge badge-neutral">${escapeHtml(projectLabel)}</span>
    <span class="summary-badge badge-info">${escapeHtml(pageLabel)}</span>
    <span class="summary-badge badge-${status.trainReady ? "success" : "neutral"}">${escapeHtml(readiness)}</span>
    <span class="summary-badge badge-neutral">${escapeHtml(t("workspace.actionsCount", { count: actionsCount }))}</span>
    <span class="summary-badge badge-${warningCount > 0 ? "warning" : "neutral"}">${escapeHtml(t("workspace.warningsCount", { count: warningCount }))}</span>
    ${notesCount > 0 ? `<span class="summary-badge badge-info">${escapeHtml(t("workspace.notesCount", { count: notesCount }))}</span>` : ""}
  `);
}

function renderProjectSummary(status, pageId = appState.currentPage) {
  const taskLabel = String(status.taskType || "--")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
  const titleEl = qs("#project-context-title");
  if (titleEl) titleEl.textContent = pageId === "dashboard" ? "Current Project" : "Project Context";

  if (!status.hasProject) {
    setHTML("#project-summary", `
      <div class="summary-empty compact">
        <p>No active project.</p>
      </div>
    `);
    return;
  }

  if (pageId === "dashboard") {
    setHTML("#project-summary", `
      <div class="path-list project-context-full">
        <div class="path-row"><span>Name</span><code>${escapeHtml(status.projectName)}</code></div>
        <div class="path-row"><span>Task</span><code>${escapeHtml(taskLabel)}</code></div>
        <div class="path-row"><span>Images</span><code>${status.imageCount}</code></div>
        <div class="path-row"><span>Annotated</span><code>${status.annotatedCount}/${status.imageCount}</code></div>
        <div class="path-row"><span>Split</span><code>${status.splitComplete ? "Ready" : "Not ready"}</code></div>
      </div>
    `);
    return;
  }

  setHTML("#project-summary", `
    <div class="project-context-compact">
      <div>
        <strong>${escapeHtml(status.projectName)}</strong>
        <span>${escapeHtml(taskLabel)}</span>
      </div>
      <span class="summary-badge badge-${status.hasDataset ? "success" : "neutral"}">${status.hasDataset ? `${status.imageCount} images` : "No images"}</span>
    </div>
  `);
}

// Dynamic Right Summary Panel Context Builders
const RIGHT_PANEL_CONFIG = {
  dashboard: buildDashboardRightPanel,
  projects: buildProjectsRightPanel,
  dataset: buildDatasetRightPanel,
  labelme: buildLabelMeRightPanel,
  split: buildSplitRightPanel,
  augmentation: buildAugmentationRightPanel,
  training: buildTrainingRightPanel,
  evaluation: buildEvaluationRightPanel,
  inference: buildInferenceRightPanel,
  "auto-labeling": buildAutoLabelingRightPanel,
  export: buildExportRightPanel,
  history: buildHistoryRightPanel,
  settings: buildSettingsRightPanel
};

// Register global browser helpers. Keep rendering logic in modules.
export function renderRightPanel(pageId, status) {
  renderProjectSummary(status, pageId);
  renderProjectAssistantContext(pageId, status);

  const evalSidebar = qs("#section-rnn-eval-summary");
  const keepEvalSidebar = pageId === "training"
    && trainingModeState.activeMode === "rnn"
    && trainingModeState.activeRnnPanel === "evaluation";
  if (evalSidebar && !keepEvalSidebar) evalSidebar.classList.add("hidden");

  const builder = RIGHT_PANEL_CONFIG[pageId];
  const container = qs("#page-context-container");
  const section = qs("#section-page-context");
  const titleEl = qs("#page-context-title");
  const actionsSection = contextCardFor("#next-actions-list");
  const warningsSection = contextCardFor("#warning-list");

  if (!container || !section) return;
  if (actionsSection) actionsSection.style.display = "";
  if (warningsSection) warningsSection.style.display = "";
  setContextCardVisible("#project-summary", true);

  const bypassEmptyPages = ["dashboard", "projects", "settings"];
  const showEmpty = !status.hasProject && !bypassEmptyPages.includes(pageId);

  if (showEmpty) {
    section.style.display = "block";
    if (titleEl) titleEl.textContent = getPageTitle(pageId);
    container.innerHTML = `
      <div class="summary-empty">
        <p>Please create or open a project first.</p>
        <button class="btn btn-secondary btn-sm" data-nav="projects">Go to Projects</button>
      </div>
    `;
    setHTML("#next-actions-list", `<li>Open Projects or Browse History to choose a project.</li>`);
    setHTML("#warning-list", `<div class="summary-warning-item">No project is open for this page.</div>`);
    updateWorkspaceContextSummary(pageId, status, {
      title: getPageTitle(pageId),
      actions: ["Open Projects or Browse History to choose a project."],
      warnings: ["No project is open for this page."]
    });
    return;
  }

  if (!builder) {
    section.style.display = "none";
    container.innerHTML = "";
    setHTML("#next-actions-list", "<li>No suggested action for this page.</li>");
    setHTML("#warning-list", "");
    updateWorkspaceContextSummary(pageId, status, {
      title: "Page Context",
      actions: ["No suggested action for this page."],
      warnings: []
    });
    return;
  }

  const config = builder(status);
  if (actionsSection) actionsSection.style.display = config.suppressActions ? "none" : "";
  if (warningsSection) warningsSection.style.display = config.suppressWarnings ? "none" : "";
  if (titleEl && config.title) titleEl.textContent = config.title;

  if (config.emptyState && !status.hasProject) {
    section.style.display = "block";
    container.innerHTML = `
      <div class="summary-empty">
        <p>${escapeHtml(config.emptyState.message)}</p>
        ${config.emptyState.actionLabel ? `<button class="btn btn-secondary btn-sm" data-nav="${escapeHtml(config.emptyState.actionNav)}">${escapeHtml(config.emptyState.actionLabel)}</button>` : ""}
      </div>
    `;
  } else {
    const rowsHtml = (config.rows || []).map(row => {
      const valEsc = escapeHtml(row.value);
      let valDom = row.isCode ? `<code>${valEsc}</code>` : valEsc;
      if (row.badgeType) {
        valDom = `<span class="summary-badge badge-${row.badgeType}">${valDom}</span>`;
      }
      return `<div class="summary-row"><span>${escapeHtml(row.label)}</span>${valDom}</div>`;
    }).join("");
    section.style.display = rowsHtml ? "block" : "none";
    container.innerHTML = rowsHtml ? `<div class="path-list" style="gap: 0;">${rowsHtml}</div>` : "";
  }

  const actions = config.actions || [];
  if (!config.suppressActions) {
    setHTML("#next-actions-list", actions.length > 0
      ? actions.map(act => `<li>${escapeHtml(act)}</li>`).join("")
      : "<li>No suggested action right now.</li>");
  } else {
    setHTML("#next-actions-list", "");
  }

  const warnings = config.warnings || [];
  const notes = config.notes || [];
  const warningTitle = contextCardFor("#warning-list")?.querySelector("h2");
  if (warningTitle) warningTitle.textContent = warnings.length > 0 ? "Warnings" : (notes.length > 0 ? "Notes" : "Warnings");
  if (!config.suppressWarnings) {
    setHTML("#warning-list", warnings.length > 0
      ? warnings.map(warn => `<div class="summary-warning-item">${escapeHtml(warn)}</div>`).join("") + notes.map(note => `<div class="summary-info-item">${escapeHtml(note)}</div>`).join("")
      : notes.map(note => `<div class="summary-info-item">${escapeHtml(note)}</div>`).join("")
    );
  } else {
    setHTML("#warning-list", "");
  }
  updateWorkspaceContextSummary(pageId, status, config);
}

function renderProjectAssistantContext(pageId, status) {
  const section = qs("#section-project-assistant-context");
  const help = qs("#project-assistant-context-help");
  const suggestions = qs("#project-assistant-context-suggestions");
  if (!section || !help || !suggestions) return;

  const config = buildProjectAssistantContext(pageId, status);
  section.style.display = config ? "block" : "none";
  const syncButton = qs("#btn-project-assistant-sync-context");
  if (syncButton) syncButton.disabled = !status.hasProject;
  if (!config) {
    help.textContent = "";
    suggestions.innerHTML = "";
    return;
  }

  help.textContent = config.help;
  const facts = (config.facts || []).map((fact) => `
    <div class="path-row">
      <span>${escapeHtml(fact.label)}</span>
      <code>${escapeHtml(fact.value)}</code>
    </div>
  `).join("");
  const prompts = (config.prompts || []).map((prompt) => `
    <div class="path-row">
      <span>${escapeHtml(prompt.label)}</span>
      <code>${escapeHtml(prompt.text)}</code>
    </div>
  `).join("");
  setHTML("#project-assistant-context-suggestions", `
    ${facts ? `<div class="assistant-context-group"><strong>Evidence</strong>${facts}</div>` : ""}
    <div class="assistant-context-group"><strong>Suggested questions</strong>${prompts}</div>
  `);
}

export function buildProjectAssistantContext(pageId, status) {
  if (!status.hasProject && pageId !== "history") return null;
  const runs = Array.isArray(appState.currentProject?.training_runs) ? appState.currentProject.training_runs : [];
  const latestRun = runs.length ? runs[runs.length - 1] : null;
  const completedRuns = runs.filter((run) => String(run.status || "").toLowerCase() === "completed");
  const models = Array.isArray(appState.models) ? appState.models : [];
  const bestModel = models.find((model) => model.weight_type === "best") || models[0] || null;
  const exportItems = Array.isArray(appState.currentProject?.exports) ? appState.currentProject.exports : [];
  const imports = Array.isArray(appState.currentProject?.imports_history) ? appState.currentProject.imports_history : [];
  const projectType = normalizeTaskLabel(status.taskType || appState.currentProject?.task_type || "--");
  const architecture = String(status.architecture || resolveAssistantArchitecture(appState.currentProject)).toLowerCase();
  const assistantPageId = resolveAssistantContextPage(pageId, architecture);
  const architectureLabel = architecture === "rnn" ? "RNN" : "CNN";
  const latestRunId = latestRun?.run_id || bestModel?.run_id || "--";
  const latestRunStatus = latestRun?.status || "--";

  const pageConfigs = {
    dashboard: {
      scope: "dashboard",
      help: t(architecture === "rnn" ? "projectAssistant.context.rnnDashboardHelp" : "projectAssistant.context.cnnDashboardHelp"),
      facts: [
        { label: t("projectAssistant.context.fact.project"), value: status.projectName || "--" },
        { label: t("projectAssistant.context.fact.architecture"), value: architectureLabel },
        { label: t("projectAssistant.context.fact.task"), value: projectType },
        { label: t("projectAssistant.context.fact.latestRun"), value: `${latestRunId} / ${latestRunStatus}` },
      ],
      prompts: [
        { label: t("projectAssistant.context.prompt.summary"), text: t(architecture === "rnn" ? "projectAssistant.context.rnnDashboardSummaryPrompt" : "projectAssistant.context.cnnDashboardSummaryPrompt", { task: projectType }) },
        { label: t("projectAssistant.context.prompt.nextStep"), text: t(architecture === "rnn" ? "projectAssistant.context.rnnDashboardNextPrompt" : "projectAssistant.context.cnnDashboardNextPrompt") },
      ],
    },
    dataset: buildDataAssistantConfig("dataset", architecture, projectType),
    labelme: buildDataAssistantConfig("labelme", architecture, projectType),
    split: buildDataAssistantConfig("split", architecture, projectType),
    augmentation: buildDataAssistantConfig("augmentation", architecture, projectType),
    training: buildTrainingAssistantConfig(architecture, projectType, latestRunId, latestRunStatus),
    evaluation: {
      scope: "evaluation",
      help: t("projectAssistant.context.evaluationHelp"),
      facts: [
        { label: t("projectAssistant.context.fact.architecture"), value: architectureLabel },
        { label: t("projectAssistant.context.fact.task"), value: projectType },
        { label: t("projectAssistant.context.fact.bestModel"), value: bestModel ? `${bestModel.weight_type || "model"} / ${bestModel.run_id || "--"}` : t("projectAssistant.context.value.noModel") },
        { label: t("projectAssistant.context.fact.completedRuns"), value: String(completedRuns.length) },
      ],
      prompts: [
        { label: t("projectAssistant.context.prompt.metric"), text: t(architecture === "rnn" ? "projectAssistant.context.rnnEvaluationMetricPrompt" : "projectAssistant.context.cnnEvaluationMetricPrompt", { task: projectType, run: latestRunId }) },
        { label: t("projectAssistant.context.prompt.risk"), text: t(architecture === "rnn" ? "projectAssistant.context.rnnEvaluationRiskPrompt" : "projectAssistant.context.cnnEvaluationRiskPrompt") },
      ],
    },
    inference: buildInferenceAssistantConfig(architecture, projectType, latestRunId),
    "auto-labeling": buildAutoLabelAssistantConfig(architecture, projectType),
    sequence_dataset: buildRnnWorkflowAssistantConfig("sequence_dataset", projectType),
    features_labels: buildRnnWorkflowAssistantConfig("features_labels", projectType),
    windowing: buildRnnWorkflowAssistantConfig("windowing", projectType),
    sequence_test: buildRnnWorkflowAssistantConfig("sequence_test", projectType),
    "model-compare": {
      scope: "model_compare",
      help: t("projectAssistant.context.compareHelp"),
      facts: [
        { label: t("projectAssistant.context.fact.architecture"), value: architectureLabel },
        { label: t("projectAssistant.context.fact.comparableRuns"), value: String(completedRuns.length) },
        { label: t("projectAssistant.context.fact.latestRun"), value: `${latestRunId} / ${latestRunStatus}` },
        { label: t("projectAssistant.context.fact.task"), value: projectType },
      ],
      prompts: [
        { label: t("projectAssistant.context.prompt.bestRun"), text: t("projectAssistant.context.compareBestRunPrompt", { task: projectType }) },
        { label: t("projectAssistant.context.prompt.artifact"), text: t("projectAssistant.context.compareArtifactPrompt") },
      ],
    },
    export: {
      scope: "export",
      help: t("projectAssistant.context.exportHelp"),
      facts: [
        { label: t("projectAssistant.context.fact.architecture"), value: architectureLabel },
        { label: t("projectAssistant.context.fact.models"), value: String(models.length) },
        { label: t("projectAssistant.context.fact.exports"), value: String(exportItems.length) },
        { label: t("projectAssistant.context.fact.bestModel"), value: bestModel ? `${bestModel.weight_type || "model"} / ${bestModel.run_id || "--"}` : t("projectAssistant.context.value.noModel") },
      ],
      prompts: [
        { label: t("projectAssistant.context.prompt.package"), text: t(architecture === "rnn" ? "projectAssistant.context.rnnExportPackagePrompt" : "projectAssistant.context.cnnExportPackagePrompt", { task: projectType }) },
        { label: t("projectAssistant.context.prompt.verify"), text: t(architecture === "rnn" ? "projectAssistant.context.rnnExportVerifyPrompt" : "projectAssistant.context.cnnExportVerifyPrompt") },
      ],
    },
    history: {
      scope: "history",
      help: t("projectAssistant.context.historyHelp"),
      facts: [
        { label: t("projectAssistant.context.fact.projects"), value: String(appState.projects?.length || 0) },
        { label: t("projectAssistant.context.fact.runs"), value: String(runs.length) },
        { label: t("projectAssistant.context.fact.imports"), value: String(imports.length) },
      ],
      prompts: [
        { label: t("projectAssistant.context.prompt.recent"), text: t("projectAssistant.context.historyRecentPrompt") },
        { label: t("projectAssistant.context.prompt.errors"), text: t("projectAssistant.context.historyErrorsPrompt") },
      ],
    },
  };
  return pageConfigs[assistantPageId] || null;
}

function resolveAssistantArchitecture(project = {}) {
  const taskType = String(project?.task_type || project?.task || "").toLowerCase();
  const explicit = String(project?.architecture || project?.training_mode || project?.training_config?.architecture || "").toLowerCase();
  if (["cnn", "rnn"].includes(explicit)) return explicit;
  return ["sequence", "time_series", "timeseries", "rnn"].some((token) => taskType.includes(token)) ? "rnn" : "cnn";
}

function resolveAssistantContextPage(pageId, architecture) {
  if (architecture !== "rnn" || pageId !== "training") return pageId;
  const panel = String(trainingModeState.activeRnnPanel || "training").replace(/-/g, "_");
  if (panel === "overview") return "dashboard";
  return panel === "model_compare" ? "model-compare" : panel;
}

function buildDataAssistantConfig(scope, architecture, projectType) {
  const isRnn = architecture === "rnn";
  return {
    scope,
    help: t(isRnn ? "projectAssistant.context.rnnDataHelp" : "projectAssistant.context.cnnDataHelp"),
    facts: [
      { label: t("projectAssistant.context.fact.architecture"), value: isRnn ? "RNN" : "CNN" },
      { label: t("projectAssistant.context.fact.task"), value: projectType },
    ],
    prompts: [
      { label: t("projectAssistant.context.prompt.readiness"), text: t(isRnn ? "projectAssistant.context.rnnDataPrompt" : "projectAssistant.context.cnnDataPrompt") },
      { label: t("projectAssistant.context.prompt.risk"), text: t(isRnn ? "projectAssistant.context.rnnDataRiskPrompt" : "projectAssistant.context.cnnDataRiskPrompt") },
    ],
  };
}

function buildTrainingAssistantConfig(architecture, projectType, latestRunId, latestRunStatus) {
  const isRnn = architecture === "rnn";
  return {
    scope: "training",
    help: t(isRnn ? "projectAssistant.context.rnnTrainingHelp" : "projectAssistant.context.cnnTrainingHelp"),
    facts: [
      { label: t("projectAssistant.context.fact.architecture"), value: isRnn ? "RNN" : "CNN" },
      { label: t("projectAssistant.context.fact.task"), value: projectType },
      { label: t("projectAssistant.context.fact.latestRun"), value: `${latestRunId} / ${latestRunStatus}` },
    ],
    prompts: [
      { label: t("projectAssistant.context.prompt.readiness"), text: t(isRnn ? "projectAssistant.context.rnnTrainingPrompt" : "projectAssistant.context.cnnTrainingPrompt") },
      { label: t("projectAssistant.context.prompt.risk"), text: t(isRnn ? "projectAssistant.context.rnnTrainingRiskPrompt" : "projectAssistant.context.cnnTrainingRiskPrompt") },
    ],
  };
}

function buildInferenceAssistantConfig(architecture, projectType, latestRunId) {
  return {
    scope: "inference",
    help: t("projectAssistant.context.inferenceHelp"),
    facts: [
      { label: t("projectAssistant.context.fact.architecture"), value: architecture === "rnn" ? "RNN" : "CNN" },
      { label: t("projectAssistant.context.fact.task"), value: projectType },
      { label: t("projectAssistant.context.fact.latestRun"), value: latestRunId },
    ],
    prompts: [{ label: t("projectAssistant.context.prompt.verify"), text: t(architecture === "rnn" ? "projectAssistant.context.rnnInferencePrompt" : "projectAssistant.context.cnnInferencePrompt") }],
  };
}

function buildAutoLabelAssistantConfig(architecture, projectType) {
  if (architecture === "rnn") return buildDataAssistantConfig("dataset", architecture, projectType);
  return {
    scope: "auto_labeling",
    help: t("projectAssistant.context.autoLabelHelp"),
    facts: [
      { label: t("projectAssistant.context.fact.architecture"), value: "CNN" },
      { label: t("projectAssistant.context.fact.task"), value: projectType },
    ],
    prompts: [
      { label: t("projectAssistant.context.prompt.readiness"), text: t("projectAssistant.context.autoLabelReadinessPrompt") },
      { label: t("projectAssistant.context.prompt.risk"), text: t("projectAssistant.context.autoLabelReviewPrompt") },
    ],
  };
}

function buildRnnWorkflowAssistantConfig(scope, projectType) {
  return {
    scope,
    help: t(`projectAssistant.context.${scope}Help`),
    facts: [
      { label: t("projectAssistant.context.fact.architecture"), value: "RNN" },
      { label: t("projectAssistant.context.fact.task"), value: projectType },
    ],
    prompts: [{ label: t("projectAssistant.context.prompt.readiness"), text: t(`projectAssistant.context.${scope}Prompt`) }],
  };
}

function normalizeTaskLabel(value) {
  return String(value || "--")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}
function getPageTitle(pageId) {
  const map = {
    dataset: "Dataset Status",
    labelme: "LabelMe Status",
    split: "Split Status",
    augmentation: "Augmentation Status",
    training: "Training Status",
    evaluation: "Evaluation Status",
    inference: "Inference Status",
    "auto-labeling": "Auto-Labeling Status",
    export: "Export Status",
    history: "History Status"
  };
  return map[pageId] || "Page Context";
}

function buildDashboardRightPanel(status) {
  const healthScore = status.hasDataset
    ? Math.round((status.annotatedCount / Math.max(status.imageCount, 1)) * 50 + (status.splitComplete ? 30 : 0) + (status.bestModelExists ? 20 : 0))
    : 0;

  const rows = status.hasProject ? [
    { label: "Health Score", value: `${healthScore}%`, badgeType: healthScore > 75 ? "success" : (healthScore > 40 ? "warning" : "danger") },
    { label: "Images", value: String(status.imageCount) },
    { label: "Annotated", value: `${status.annotatedCount}/${status.imageCount}` },
    { label: "Split", value: status.splitComplete ? "Ready" : "Not ready", badgeType: status.splitComplete ? "success" : "danger" },
    { label: "Best Model", value: status.bestModelExists ? "Exists" : "None", badgeType: status.bestModelExists ? "success" : "neutral" }
  ] : [];

  const actions = [];
  if (!status.hasProject) actions.push("Create a new project or open one from Browse History.");
  else if (!status.hasDataset) actions.push("Import images or extracted video frames in Dataset.");
  else if (!status.labelme.synced) actions.push("Sync LabelMe JSON and review annotation issues.");
  else if (!status.splitComplete) actions.push("Create Train / Val / Test split.");
  else actions.push("Open Training and start a configured run.");

  const warnings = [];
  if (!status.hasProject) warnings.push("No active project. Most workflow actions are waiting for a project.");
  else if (!status.hasDataset) warnings.push("The active project has no imported images.");

  return {
    title: "Project Readiness",
    rows,
    actions,
    warnings,
    emptyState: !status.hasProject ? {
      message: "Create or open a project to see dashboard readiness.",
      actionLabel: "Browse History",
      actionNav: "history"
    } : null
  };
}

function buildProjectsRightPanel(status) {
  return {
    title: "Projects Status",
    rows: [
      { label: "Total Projects", value: String(appState.projects?.length || 0) },
      { label: "Active Project", value: status.hasProject ? status.projectName : "None", isCode: true }
    ],
    actions: ["Use New Project to create a project.", "Use Browse History to open an existing project."],
    warnings: appState.projects?.length === 0 ? ["No projects are available yet."] : []
  };
}

function buildDatasetRightPanel(status) {
  const images = appState.currentProject?.images || [];
  const videos = new Set(images.map(img => img.source_video).filter(Boolean));
  const duplicates = images.filter(img => img.quality?.is_duplicate).length;
  const invalid = images.filter(img => img.quality?.is_corrupted).length;
  const score = status.hasDataset ? Math.max(0, 100 - (duplicates * 5) - (invalid * 10)) : 0;

  const warnings = [];
  if (!status.hasDataset) warnings.push("No images imported. Dataset-dependent actions are disabled.");
  if (duplicates > 0) warnings.push(`${duplicates} possible duplicate images detected.`);
  if (invalid > 0) warnings.push(`${invalid} corrupted or invalid files detected.`);

  return {
    title: "Dataset Status",
    rows: [
      { label: "Images", value: String(status.imageCount) },
      { label: "Videos", value: String(videos.size) },
      { label: "Quality", value: status.hasDataset ? `${score}/100` : "Not run", badgeType: score > 80 ? "success" : (score > 50 ? "warning" : "neutral") },
      { label: "Duplicates", value: String(duplicates), badgeType: duplicates > 0 ? "warning" : null },
      { label: "Invalid", value: String(invalid), badgeType: invalid > 0 ? "danger" : null }
    ],
    actions: ["Import images or a folder.", "Run quality check before labeling.", "Open LabelMe after images are ready."],
    warnings
  };
}

function buildLabelMeRightPanel(status) {
  const lm = appState.labelme || {};
  const warnings = [];
  if (!status.hasDataset) warnings.push(t("labelme.empty.noImages"));
  if ((lm.missingJson || 0) > 0) warnings.push(`${lm.missingJson} images are missing LabelMe JSON.`);
  if ((lm.invalidJson || 0) > 0) warnings.push(`${lm.invalidJson} invalid JSON files need review.`);
  if ((lm.unknownLabels || 0) > 0) warnings.push(`${lm.unknownLabels} unknown labels are not in the project class list.`);

  return {
    title: "LabelMe Status",
    rows: [
      { label: "Images", value: String(status.imageCount) },
      { label: "JSON", value: String(lm.jsonCount || 0) },
      { label: "Missing", value: String(lm.missingJson || 0), badgeType: lm.missingJson > 0 ? "warning" : null },
      { label: "Invalid", value: String(lm.invalidJson || 0), badgeType: lm.invalidJson > 0 ? "danger" : null },
      { label: "Completion", value: `${status.labelme.completionRate || 0}%`, badgeType: (status.labelme.completionRate || 0) >= 95 ? "success" : "neutral" }
    ],
    actions: ["Open LabelMe with the project image folder.", "Rescan annotation status after editing.", "Review invalid or unknown labels before Split."],
    warnings
  };
}

function buildSplitRightPanel(status) {
  const warnings = [];
  if (!status.splitComplete) warnings.push("Train / Val / Test split is not ready. Training cannot start safely.");
  if ((status.splitCounts.val || 0) === 0 && status.splitComplete) warnings.push("Validation set count is 0. Recreate the split with validation data.");

  return {
    title: "Split Status",
    rows: [
      { label: "Train", value: String(status.splitCounts.train || 0) },
      { label: "Val", value: String(status.splitCounts.val || 0) },
      { label: "Test", value: String(status.splitCounts.test || 0) },
      { label: "Quality", value: `${status.splitQuality || 0}/100`, badgeType: status.splitQuality > 80 ? "success" : "neutral" },
      { label: "Leakage Risk", value: status.splitComplete ? "Low" : "Unknown", badgeType: status.splitComplete ? "success" : "warning" }
    ],
    actions: [],
    warnings: [],
    suppressActions: true,
    suppressWarnings: true
  };
}

function buildAugmentationRightPanel(status) {
  const multiplier = parseInt(qs("#aug-multiplier")?.value || qs("#multiplier")?.value || "1", 10);
  const trainCount = status.splitCounts.train || 0;
  const valCount = status.splitCounts.val || 0;
  const testCount = status.splitCounts.test || 0;
  const valTestCount = valCount + testCount;
  const readinessState = qs("#aug-readiness-card")?.dataset?.state || "blocked_no_project";
  const previewReady = readinessState === "preview_ready";
  const previewStale = readinessState === "preview_stale";
  const hasPreviewImage = Boolean(qs("#aug-preview-select-img")?.value);
  const generatedCopies = trainCount * multiplier;

  let statusLabel = "Blocked";
  let riskLabel = "Blocked";
  if (status.hasProject && status.hasDataset && status.splitComplete && trainCount > 0) {
    statusLabel = previewReady ? "Preview ready" : "Ready";
    riskLabel = previewReady ? "Low" : (previewStale ? "Preview stale" : "Preview required");
  }

  const actions = [];
  const warnings = [];
  const notes = ["Val/Test images are not augmented; augmentation is applied to the train split only."];
  if (!status.hasProject) {
    actions.push("Create or open a project first.");
    warnings.push("No active project.");
  } else if (!status.hasDataset) {
    actions.push("Import images in Dataset.");
    actions.push("Sync annotations in LabelMe.");
    actions.push("Create a Train / Val / Test split.");
    warnings.push("Dataset is missing, so augmentation cannot run.");
  } else if (!status.splitComplete || trainCount === 0) {
    actions.push("Create a Train / Val / Test split.");
    warnings.push("Train-only augmentation requires a ready split.");
  } else if (!hasPreviewImage) {
    actions.push("Select a train image for preview.");
    warnings.push("No preview image is selected.");
  } else if (previewStale) {
    actions.push("Regenerate the preview.");
    actions.push("Run the risk check.");
    warnings.push("The preview may be stale after settings changed.");
  } else if (!previewReady) {
    actions.push("Choose an augmentation preset.");
    actions.push("Generate a preview.");
    actions.push("Run the risk check.");
  } else {
    actions.push("Review the preview result.");
    actions.push("Confirm the train split target.");
    actions.push("Start the augmentation job.");
  }

  return {
    title: "Augmentation Status",
    rows: [
      { label: "Status", value: statusLabel, badgeType: previewReady ? "success" : (statusLabel === "Ready" ? "warning" : "danger") },
      { label: "Target", value: "Train split", isCode: true },
      { label: "Output", value: `+${generatedCopies}`, isCode: true },
      { label: "Risk", value: riskLabel, badgeType: previewReady ? "success" : "warning" }
    ],
    actions: [],
    warnings: [],
    notes: [],
    suppressActions: true,
    suppressWarnings: true
  };
}

function buildTrainingRightPanel(status) {
  if (isRnnTrainingWorkspaceActive("training")) {
    return buildRnnTrainingRightPanel(status);
  }

  const gpu = appState.systemHealth?.device?.device_name || "CPU";
  const model = qs("#train-model")?.value || "--";
  const runs = appState.currentProject?.training_runs || [];
  const latestRun = runs.length > 0 ? runs[runs.length - 1] : null;
  const runStatus = latestRun?.status ?? "--";
  const statusBadge = runStatus === "completed" ? "success" : runStatus === "failed" ? "danger" : runStatus === "training" ? "warning" : "neutral";

  const warnings = [];
  if (!status.hasDataset) warnings.push("Dataset is missing. Import images before training.");
  if (!status.labelme.synced) warnings.push("LabelMe annotations are not synced.");
  if (!status.splitComplete) warnings.push("Train / Val / Test split is missing.");
  if (gpu === "CPU" || gpu.includes("unavailable") || gpu.includes("Backend")) warnings.push("GPU is unavailable or backend health is missing; training may be slow.");

  const actions = [];
  if (!status.hasDataset) actions.push("Go to Dataset and import images.");
  if (status.hasDataset && !status.labelme.synced) actions.push("Go to LabelMe and sync annotations.");
  if (status.hasDataset && status.labelme.synced && !status.splitComplete) actions.push("Create Train / Val / Test split.");
  if (status.trainReady) actions.push("Review settings, then start training.");

  return {
    title: "Training Context",
    rows: [
      { label: "Start status", value: status.trainReady ? "Ready" : "Blocked", badgeType: status.trainReady ? "success" : "danger" },
      { label: "Dataset", value: status.hasDataset ? `${status.imageCount} images` : "Missing", badgeType: status.hasDataset ? "success" : "danger" },
      { label: "Labels", value: status.labelme.synced ? `${status.annotatedCount}/${status.imageCount}` : "Not synced", badgeType: status.labelme.synced ? "success" : "danger" },
      { label: "Split", value: status.splitComplete ? `${status.splitCounts.train}/${status.splitCounts.val}/${status.splitCounts.test}` : "Missing", badgeType: status.splitComplete ? "success" : "danger" },
      { label: "Model", value: model },
      { label: "Hardware", value: gpu, isCode: true },
      { label: "Run", value: latestRun?.run_id ?? "--", isCode: true },
      { label: "Run status", value: runStatus, badgeType: statusBadge }
    ],
    actions: [],
    warnings: [],
    suppressActions: true,
    suppressWarnings: true
  };
}

function buildRnnTrainingRightPanel(status) {
  const readiness = trainingModeState.rnn.readiness || {};
  const csv = readiness.summary?.csv || {};
  const config = trainingModeState.rnn.config || {};
  const runs = (appState.currentProject?.training_runs || []).filter((run) =>
    String(run.architecture || run.model_family || run.backend || "").toLowerCase().includes("rnn")
      || String(run.model_id || run.run_id || "").toLowerCase().includes("rnn")
      || String(run.model_type || "").toLowerCase().includes("lstm")
      || String(run.model_type || "").toLowerCase().includes("gru")
      || String(run.model_type || "").toLowerCase().includes("bilstm")
  );
  const latestRun = runs.length > 0 ? runs[runs.length - 1] : null;
  const isReady = readiness.ready === true || csv.valid === true;
  const panelLabel = String(trainingModeState.activeRnnPanel || "overview").replace(/-/g, " ");
  const featureDim = csv.feature_dim || config.feature_dim || (Array.isArray(config.feature_columns) ? config.feature_columns.length : 0);
  const runStatus = latestRun?.status ?? "--";
  const statusBadge = runStatus === "completed" ? "success" : runStatus === "failed" ? "danger" : runStatus === "training" ? "warning" : "neutral";

  return {
    title: "RNN Context",
    rows: [
      { label: "Panel", value: panelLabel || "overview" },
      { label: "Sequence data", value: isReady ? "Ready" : "Not ready", badgeType: isReady ? "success" : "warning" },
      { label: "CSV files", value: String(csv.file_count || 0), badgeType: (csv.file_count || 0) > 0 ? "success" : "neutral" },
      { label: "Sequences", value: String(csv.sequence_count || 0) },
      { label: "Feature dim", value: featureDim ? String(featureDim) : "--" },
      { label: "Backend", value: trainingModeState.rnn.backend || "--", isCode: true },
      { label: "Run", value: latestRun?.run_id ?? "--", isCode: true },
      { label: "Run status", value: runStatus, badgeType: statusBadge }
    ],
    actions: [],
    warnings: [],
    suppressActions: true,
    suppressWarnings: true
  };
}

function buildEvaluationRightPanel(status) {
  const models = appState.models || [];
  const model = models.find(m => m.weight_type === "best") || models[0];
  const formatNum = (v) => (v === null || v === undefined) ? "--" : Number(v).toFixed(3);

  return {
    title: "Evaluation Status",
    rows: [
      { label: "mAP50", value: model ? formatNum(model.best_map50_m) : "--", isCode: true },
      { label: "mAP50-95", value: model ? formatNum(model.best_map50_95_m) : "--", isCode: true },
      { label: "Precision", value: model ? formatNum(model.precision) : "--" },
      { label: "Recall", value: model ? formatNum(model.recall) : "--" },
      { label: "Model", value: model ? model.weight_type : "--", isCode: true },
      { label: "Run", value: model?.run_id ?? "--", isCode: true }
    ],
    actions: ["Run evaluation after a best model exists.", "Review confusion matrix and failure cases."],
    warnings: !status.bestModelExists ? ["No trained best model found yet."] : []
  };
}

function buildInferenceRightPanel(status) {
  const models = appState.models || [];
  const bestCount = models.filter((m) => m.weight_type === "best").length;
  const lastCount = models.filter((m) => m.weight_type === "last").length;
  const latestRun = models.length > 0 ? (models[0]?.run_id ?? "--") : "--";
  const selId = appState.inferenceSelectedModelId;
  const selModel = selId ? models.find((m) => m.model_id === selId) : null;

  const warnings = [];
  if (models.length === 0) warnings.push("No trained weights found. Complete Training first.");

  return {
    title: "Inference Lab Status",
    rows: [
      { label: "Models", value: String(models.length) },
      { label: "best.pt", value: String(bestCount) },
      { label: "last.pt", value: String(lastCount) },
      { label: "Latest Run", value: latestRun, isCode: true },
      { label: "Selected", value: selModel ? `${selModel.weight_type} (${selModel.run_id || "?"})` : "--", isCode: true }
    ],
    actions: ["Select a registered model.", "Upload one test image.", "Run single-image inference."],
    warnings
  };
}

function buildAutoLabelingRightPanel(status) {
  const models = appState.models || [];
  const compatibleModels = models.filter((model) => {
    const projectTask = String(status.taskType || "").toLowerCase();
    const modelTask = String(model.task_type || "").toLowerCase();
    if (!projectTask || !modelTask) return true;
    if (projectTask.includes("segmentation")) return modelTask.includes("segmentation");
    if (projectTask.includes("detection")) return modelTask.includes("detection");
    if (projectTask.includes("classification")) return modelTask.includes("classification");
    return true;
  });

  const warnings = ["Draft annotations must be reviewed before applying to current labels."];
  if (models.length === 0) warnings.unshift("No model available for auto-labeling. Train or import a model first.");
  if (models.length > 0 && compatibleModels.length === 0) warnings.unshift("Available models do not match the project task type.");

  return {
    title: "Auto-Labeling Status",
    rows: [
      { label: "Models", value: String(models.length) },
      { label: "Compatible", value: String(compatibleModels.length), badgeType: compatibleModels.length > 0 ? "success" : "warning" },
      { label: "Output", value: "Draft only", badgeType: "neutral" },
      { label: "Format", value: "LabelMe / YOLO", isCode: true },
      { label: "Backend", value: "Draft API ready", badgeType: "success" }
    ],
    actions: ["Choose input images.", "Select best.pt or last.pt.", "Generate drafts, then review before apply."],
    warnings
  };
}

function buildExportRightPanel(status) {
  const models = appState.models || [];
  const bestModel = models.find((m) => m.weight_type === "best");
  return {
    title: "Export Status",
    rows: [
      { label: "Weights", value: String(models.length) },
      { label: "Best Run", value: bestModel?.run_id ?? "--", isCode: true },
      { label: "ONNX", value: status.bestModelExists ? "Ready" : "Unavailable", badgeType: status.bestModelExists ? "success" : "neutral" },
      { label: "Report", value: "Ready", badgeType: "success" }
    ],
    actions: ["Select a model artifact.", "Export ONNX or report.", "Verify exported package before deployment."],
    warnings: !status.bestModelExists ? ["No best model is available for export."] : []
  };
}

function buildHistoryRightPanel(status) {
  const runs = appState.currentProject?.training_runs?.length || 0;
  const imports = appState.currentProject?.imports_history?.length || 0;
  return {
    title: "History Status",
    rows: [
      { label: "Projects", value: String(appState.projects?.length || 0) },
      { label: "Runs", value: String(runs) },
      { label: "Imports", value: String(imports) }
    ],
    actions: ["Open Browse History for project file details.", "Review recent imports, runs, and exports."],
    warnings: []
  };
}

function buildSettingsRightPanel(status) {
  const gpu = appState.systemHealth?.device?.device_name || "Backend unavailable";
  const path = status.datasetPath ? (status.datasetPath.length > 25 ? "..." + status.datasetPath.slice(-22) : status.datasetPath) : "--";
  const isHealthy = appState.systemHealth?.status === "healthy";
  return {
    title: "Settings Status",
    rows: [
      { label: "Dataset Path", value: path, isCode: true },
      { label: "Device", value: gpu },
      { label: "LabelMe", value: status.labelme.backendReady ? "Connected" : "Disconnected", badgeType: status.labelme.backendReady ? "success" : "danger" },
      { label: "API", value: isHealthy ? "Healthy" : "Offline", badgeType: isHealthy ? "success" : "danger" }
    ],
    actions: ["Switch language or theme.", "Use diagnostics if the backend is offline."],
    warnings: !isHealthy ? ["API health check failed or backend is unavailable."] : []
  };
}
