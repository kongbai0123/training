import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { qs, setHTML, escapeHtml } from "../utils.js";
import { getDirtyFormSummaries } from "../core/dirty_forms.js";
import { getStaleResources } from "../core/resource_freshness.js";
import { buildCnnGuidedWizard, renderCnnGuidedWizard } from "../core/cnn_guided_wizard.js";

export function initDashboard() {
  qs("#btn-dashboard-refresh")?.addEventListener("click", () => {
    eventBus.emit("refresh-project");
  });
}

export function renderDashboard(status) {
  setHTML("#dashboard-kpis", "");
  renderDashboardAlerts();
  renderWorkflowMap(status);
  renderRecentProjects(appState.projects);
  renderActivity(status);
}

function renderDashboardAlerts() {
  const dirtyForms = getDirtyFormSummaries();
  const staleResources = getStaleResources();
  const alerts = [];
  if (dirtyForms.length) {
    alerts.push(`
      <div class="status-guard warning dashboard-operational-alert" data-ui-smoke="dirty-form-alert">
        <strong>Unsaved changes</strong>
        <span>${escapeHtml(dirtyForms.map((item) => item.label).join(", "))}</span>
      </div>
    `);
  }
  staleResources.forEach((item) => {
    alerts.push(`
      <div class="status-guard warning dashboard-operational-alert" data-ui-smoke="stale-resource-alert">
        <strong>${escapeHtml(item.label)}</strong>
        <span>${escapeHtml(item.message)}</span>
        <button type="button" class="btn btn-secondary btn-sm" data-refresh-project>${escapeHtml(item.action)}</button>
      </div>
    `);
  });
  setHTML("#dashboard-alerts", alerts.join(""));
  qs("#dashboard-alerts")?.querySelectorAll("[data-refresh-project]").forEach((button) => {
    button.addEventListener("click", () => eventBus.emit("refresh-project"));
  });
}

function renderWorkflowMap(status) {
  const wizard = buildCnnGuidedWizard(status, appState);
  const workflow = [
    {
      step: 1,
      icon: "fa-folder-open",
      title: "Dataset",
      page: "dataset",
      accent: "violet",
      badge: status.hasDataset ? "Ready" : "Not started",
      badgeClass: status.hasDataset ? "success" : "muted",
      rows: [["Images", status.imageCount], ["Quality check", appState.currentProject?.dataset_health ? "Done" : "Not run"]],
      progress: status.hasDataset ? 100 : 0,
      action: "Manage Dataset",
    },
    {
      step: 2,
      icon: "fa-pen-nib",
      title: "Annotation",
      page: "labelme",
      accent: "green",
      badge: status.labelme.synced ? "Synced" : "Not started",
      badgeClass: status.labelme.synced ? "success" : "muted",
      rows: [["Annotated", `${status.annotatedCount}/${status.imageCount}`], ["Coverage", `${status.labelme.completionRate || 0}%`]],
      progress: status.labelme.completionRate || 0,
      action: "Open LabelMe",
    },
    {
      step: 3,
      icon: "fa-robot",
      title: "Auto-Labeling",
      page: "auto-labeling",
      accent: "cyan",
      badge: "Not started",
      badgeClass: "muted",
      rows: [["Drafts", 0], ["Models", appState.models?.length || 0]],
      progress: 0,
      action: "Start Auto-Labeling",
    },
    {
      step: 4,
      icon: "fa-code-branch",
      title: "Split",
      page: "split",
      accent: "orange",
      badge: status.splitComplete ? "Ready" : "Not ready",
      badgeClass: status.splitComplete ? "success" : "danger",
      rows: [["Train / Val / Test", `${status.splitCounts.train || "-"} / ${status.splitCounts.val || "-"} / ${status.splitCounts.test || "-"}`], ["Split file", status.splitComplete ? "Ready" : "None"]],
      progress: status.splitComplete ? 100 : 0,
      action: "Create Split",
    },
    {
      step: 5,
      icon: "fa-wand-magic-sparkles",
      title: "Augmentation",
      page: "augmentation",
      accent: "amber",
      badge: appState.currentProject?.augmentation_config ? "Configured" : "Not started",
      badgeClass: appState.currentProject?.augmentation_config ? "success" : "muted",
      rows: [["Policies", appState.currentProject?.augmentation_config ? 1 : 0], ["Active", appState.currentProject?.augmentation_config ? "Yes" : "No"]],
      progress: appState.currentProject?.augmentation_config ? 100 : 0,
      action: "Configure Augmentation",
    },
    {
      step: 6,
      icon: "fa-microchip",
      title: "Training",
      page: "training",
      accent: "blue",
      badge: status.trainReady ? "Ready" : "Not started",
      badgeClass: status.trainReady ? "success" : "muted",
      rows: [["Runs", appState.currentProject?.training_runs?.length || 0], ["Best mAP", "--"]],
      progress: status.bestModelExists ? 100 : status.trainReady ? 60 : 0,
      action: "Start Training",
    },
    {
      step: 7,
      icon: "fa-chart-line",
      title: "Evaluation",
      page: "evaluation",
      accent: "purple",
      badge: status.bestModelExists ? "Available" : "Not started",
      badgeClass: status.bestModelExists ? "success" : "muted",
      rows: [["Evaluations", 0], ["Best mAP", "--"]],
      progress: status.bestModelExists ? 70 : 0,
      action: "Run Evaluation",
    },
    {
      step: 8,
      icon: "fa-flask",
      title: "Inference Lab",
      page: "inference",
      accent: "indigo",
      badge: appState.models?.length ? "Available" : "Not started",
      badgeClass: appState.models?.length ? "success" : "muted",
      rows: [["Models", appState.models?.length || 0], ["Tests", 0]],
      progress: appState.models?.length ? 50 : 0,
      action: "Open Inference Lab",
    },
    {
      step: 9,
      icon: "fa-box-archive",
      title: "Export",
      page: "export",
      accent: "teal",
      badge: status.bestModelExists ? "Ready" : "Not ready",
      badgeClass: status.bestModelExists ? "success" : "danger",
      rows: [["Exports", 0], ["Last export", "--"]],
      progress: status.bestModelExists ? 80 : 0,
      action: "Export Model",
    },
  ];

  setHTML("#control-cards", `
    ${renderCnnGuidedWizard(wizard)}
    <details class="workflow-map-panel workflow-map-details">
      <summary class="workflow-map-summary">
        <span><i class="fa-solid fa-map"></i> Detailed Workflow Map</span>
        <small>Open when you need stage-level metrics and direct page shortcuts.</small>
      </summary>
      <div class="section-title workflow-map-title">
        <div>
          <h2><i class="fa-solid fa-map"></i> Workflow Details</h2>
          <p>Detailed project progress by stage. Use Guided Wizard above for the primary next action.</p>
        </div>
      </div>
      <div class="workflow-grid">
        ${workflow.map(renderWorkflowCard).join("")}
      </div>
    </details>
  `);
}

function renderWorkflowCard(card) {
  return `
    <article class="workflow-card workflow-${card.accent}">
      <div class="workflow-card-top">
        <div class="workflow-title">
          <i class="fa-solid ${card.icon}"></i>
          <h3>${card.step}. ${escapeHtml(card.title)}</h3>
        </div>
        <span class="badge badge-${card.badgeClass}">${escapeHtml(card.badge)}</span>
      </div>
      <div class="workflow-card-rows">
        ${card.rows.map(([label, value]) => `
          <div class="workflow-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
        `).join("")}
      </div>
      <div class="progress-block">
        <div class="progress-track"><div class="progress-fill" style="width:${Number(card.progress) || 0}%"></div></div>
        <div class="progress-row"><span></span><strong>${Number(card.progress) || 0}%</strong></div>
      </div>
      <button class="btn btn-secondary btn-sm btn-block" data-nav="${escapeHtml(card.page)}">${escapeHtml(card.action)}</button>
    </article>
  `;
}

function renderRecentProjects(projects) {
  eventBus.emit("render-recent-projects-list", (projects || []).slice(0, 3));
}

function renderActivity(status) {
  const items = [];
  if (!status.hasProject) {
    items.push("No active project. Create a new project or open one from Browse History.");
  } else if (!status.hasDataset) {
    items.push("Project is open, but no dataset has been imported yet. Start from Dataset.");
  } else if (!status.splitComplete) {
    items.push("Dataset exists. Sync annotations and create a Train / Val / Test split before training.");
  } else if (!status.trainReady) {
    items.push("Split exists, but training readiness still has blockers. Review Training status.");
  } else {
    items.push("Project is ready for training. Open Training to review config and start a run.");
  }

  setHTML("#recent-activity-list", items.map((item) => `<div class="activity-item">${escapeHtml(item)}</div>`).join(""));
}
