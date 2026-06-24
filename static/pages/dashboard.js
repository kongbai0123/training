import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { qs, setHTML, escapeHtml } from "../utils.js";

export function initDashboard() {
  qs("#btn-dashboard-refresh")?.addEventListener("click", () => {
    eventBus.emit("refresh-project");
  });

  qs("#control-cards")?.addEventListener("click", (event) => {
    const card = event.target.closest(".control-card[data-dashboard-card]");
    if (!card) return;
    appState.dashboardFocus = card.dataset.dashboardCard || "overview";
    eventBus.emit("state-changed");
  });
}

export function renderDashboard(status) {
  renderDashboardAlerts();
  renderProjectCommandBar(status);
  renderKpis(status);
  renderControlCards(status);
  renderActivity(status);
}

function renderDashboardAlerts() {
  setHTML("#dashboard-alerts", "");
}

function renderProjectCommandBar(status) {
  const project = appState.currentProject;
  const healthScore = getProjectHealthScore(status);
  const updatedAt = formatDate(project?.updated_at || project?.created_at);
  const projectTitle = status.hasProject ? status.projectName : "No project opened";
  const projectMeta = status.hasProject
    ? `${status.taskType || "vision"} · ${status.imageCount > 0 ? `${status.imageCount} images` : "No images imported"} · Health ${healthScore}%`
    : "Create or open a project to start the workflow.";
  const primaryAction = status.hasProject
    ? `<button class="btn btn-primary" data-nav="dataset"><i class="fa-solid fa-play"></i> Continue Project</button>`
    : `<button class="btn btn-primary" data-nav="projects"><i class="fa-solid fa-plus"></i> Create Project</button>`;

  setHTML("#project-command-bar", `
    <section class="project-command-bar">
      <div class="project-command-main">
        <span class="eyebrow">Current Project</span>
        <h2>${escapeHtml(projectTitle)}</h2>
        <p>${escapeHtml(projectMeta)}</p>
      </div>
      <div class="project-command-status">
        <div class="health-ring" aria-label="Project health ${healthScore}%">
          <strong>${healthScore}%</strong>
          <span>Health</span>
        </div>
        <div class="project-command-updated">
          <span>Updated</span>
          <strong>${escapeHtml(updatedAt || "--")}</strong>
        </div>
      </div>
      <div class="project-command-actions">
        ${primaryAction}
        <button class="btn btn-secondary" data-nav="projects"><i class="fa-solid fa-folder-open"></i> Open Project</button>
        <button class="btn btn-secondary" data-nav="history"><i class="fa-solid fa-clock-rotate-left"></i> Browse History</button>
      </div>
    </section>
  `);
}

function renderKpis(status) {
  const items = [
    ["Dataset", status.hasDataset ? `${status.imageCount} images` : "No images imported"],
    ["Annotation", status.imageCount > 0 ? `${status.annotatedCount}/${status.imageCount}` : "Unavailable"],
    ["Split", status.splitComplete ? "Ready" : "Not ready"],
    ["Training", productTrainingLabel(status)]
  ];
  setHTML("#dashboard-kpis", items.map(([label, value]) => `
    <div class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join(""));
}

function renderControlCards(status) {
  const cards = [
    {
      key: "dataset",
      icon: "fa-images",
      title: "Dataset",
      badge: status.hasDataset ? "Ready" : "Needs data",
      badgeClass: status.hasDataset ? "success" : "warning",
      progressText: status.hasDataset ? `${status.imageCount} images` : "No images imported",
      progress: status.hasDataset ? 100 : 0,
      primary: button("Manage Dataset", "dataset", "primary")
    },
    {
      key: "labelme",
      icon: "fa-pen-nib",
      title: "Annotation",
      badge: status.labelme.synced ? "Synced" : "Needs sync",
      badgeClass: status.labelme.synced ? "success" : "warning",
      progressText: status.imageCount > 0 ? `${status.annotatedCount}/${status.imageCount} annotated` : "Annotation unavailable",
      progress: status.labelme.completionRate || 0,
      primary: button("Open LabelMe", "labelme", "primary")
    },
    {
      key: "auto-labeling",
      icon: "fa-wand-magic-sparkles",
      title: "Auto-Labeling",
      badge: status.bestModelExists ? "Model available" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      progressText: `${status.unannotatedCount} unlabeled images`,
      progress: status.bestModelExists ? 70 : 15,
      primary: button("Create Drafts", "auto-labeling", "primary")
    },
    {
      key: "split",
      icon: "fa-code-branch",
      title: "Split",
      badge: status.splitComplete ? "Ready" : "Not ready",
      badgeClass: status.splitComplete ? "success" : "warning",
      progressText: `Train ${status.splitCounts.train} · Val ${status.splitCounts.val} · Test ${status.splitCounts.test}`,
      progress: status.splitComplete ? 100 : 0,
      primary: button("Configure Split", "split", "primary")
    },
    {
      key: "augmentation",
      icon: "fa-layer-group",
      title: "Augmentation",
      badge: appState.currentProject?.augmentation_config ? "Configured" : "Optional",
      badgeClass: appState.currentProject?.augmentation_config ? "success" : "neutral",
      progressText: "Train-set only",
      progress: appState.currentProject?.augmentation_config ? 100 : 35,
      primary: button("Open Settings", "augmentation", "primary")
    },
    {
      key: "training",
      icon: "fa-microchip",
      title: "Training",
      badge: status.trainReady ? "Ready" : "Blocked",
      badgeClass: status.trainReady ? "success" : "danger",
      progressText: status.trainReady ? "Ready to start" : `${status.blockers.length} blockers`,
      progress: status.trainReady ? 100 : 25,
      primary: button("Open Training", "training", "primary")
    },
    {
      key: "evaluation",
      icon: "fa-chart-line",
      title: "Evaluation",
      badge: status.bestModelExists ? "Available" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      progressText: status.bestModelExists ? "Model metrics available" : "Train a model first",
      progress: status.bestModelExists ? 100 : 0,
      primary: button("View Results", "evaluation", "primary")
    },
    {
      key: "inference",
      icon: "fa-vial-circle-check",
      title: "Inference Lab",
      badge: (appState.models || []).length > 0 ? "Ready" : "No weights",
      badgeClass: (appState.models || []).length > 0 ? "success" : "warning",
      progressText: `${(appState.models || []).length} available weights`,
      progress: (appState.models || []).length > 0 ? 100 : 0,
      primary: button("Test Model", "inference", "primary")
    },
    {
      key: "export",
      icon: "fa-file-export",
      title: "Export",
      badge: status.bestModelExists ? "Ready" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      progressText: status.bestModelExists ? "Export package available" : "No trained model",
      progress: status.bestModelExists ? 100 : 0,
      primary: button("Open Export", "export", "primary")
    }
  ];

  setHTML("#control-cards", cards.map(renderControlCard).join(""));
}

function renderControlCard(card) {
  const active = appState.dashboardFocus === card.key ? " active" : "";
  return `
    <article class="control-card${active}" data-dashboard-card="${escapeHtml(card.key)}" tabindex="0">
      <div class="card-heading"><i class="fa-solid ${card.icon}"></i><h3>${escapeHtml(card.title)}</h3></div>
      <span class="badge badge-${card.badgeClass}">${escapeHtml(card.badge)}</span>
      <div class="workflow-progress-label">${escapeHtml(card.progressText)}</div>
      <div class="progress-block">
        <div class="progress-track"><div class="progress-fill" style="width:${Number(card.progress) || 0}%"></div></div>
      </div>
      <div class="card-actions">${card.primary}</div>
    </article>
  `;
}

function button(label, page, type) {
  return `<button class="btn btn-${type}" data-nav="${page}">${escapeHtml(label)}</button>`;
}

function renderActivity(status) {
  const events = buildMeaningfulEvents(status);
  if (events.length === 0) {
    setHTML("#recent-activity-list", `
      <div class="empty-activity">
        <strong>No activity yet.</strong>
        <span>Import images or open a project to begin.</span>
      </div>
    `);
    return;
  }

  setHTML("#recent-activity-list", events.slice(0, 5).map((item) => `
    <div class="activity-item">
      <strong>${escapeHtml(item.title)}</strong>
      <span>${escapeHtml(item.detail)}</span>
    </div>
  `).join(""));
}

function buildMeaningfulEvents(status) {
  const project = appState.currentProject;
  if (!project) return [];
  const events = [];

  const imports = project.imports_history || project.import_history || [];
  if (imports.length > 0) {
    const latest = imports[imports.length - 1];
    const count = latest.uploaded_count ?? latest.imported_count ?? latest.count ?? 0;
    events.push({
      title: `Imported ${count} files`,
      detail: formatDate(latest.timestamp || latest.created_at) || "Latest dataset import"
    });
  } else if (status.hasDataset) {
    events.push({
      title: `Dataset contains ${status.imageCount} images`,
      detail: "Ready for annotation review"
    });
  }

  if (status.labelme.jsonCount > 0) {
    events.push({
      title: `Synced ${status.labelme.jsonCount} LabelMe JSON files`,
      detail: `${status.labelme.completionRate || 0}% annotation coverage`
    });
  }

  if (status.splitComplete) {
    events.push({
      title: "Created Train / Val / Test split",
      detail: `Train ${status.splitCounts.train}, Val ${status.splitCounts.val}, Test ${status.splitCounts.test}`
    });
  }

  const runs = project.training_runs || [];
  if (runs.length > 0) {
    const latestRun = runs[runs.length - 1];
    events.push({
      title: `Training ${latestRun.status || "run"}: ${latestRun.run_id || "latest run"}`,
      detail: latestRun.best_map50_95_m ? `Best mAP50-95 ${Number(latestRun.best_map50_95_m).toFixed(3)}` : "Training record available"
    });
  }

  if (status.bestModelExists) {
    events.push({
      title: "Model weights available",
      detail: "Evaluation, inference, and export can use the trained model"
    });
  }

  return events;
}

function productTrainingLabel(status) {
  if (status.trainingRunning) return "Running";
  if (status.bestModelExists) return "Completed";
  if (status.trainReady) return "Ready";
  return "Not ready";
}

function getProjectHealthScore(status) {
  let score = 0;
  if (status.hasProject) score += 10;
  if (status.hasDataset) score += 20;
  if (status.annotationRate >= 95) score += 25;
  else if (status.annotationRate > 0) score += Math.round(status.annotationRate * 0.2);
  if (status.splitComplete) score += 20;
  if (status.bestModelExists) score += 15;
  if (appState.currentProject?.current?.export_id) score += 10;
  return Math.min(100, score);
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).replace("T", " ").slice(0, 16);
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}
