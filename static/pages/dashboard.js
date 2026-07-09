import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
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
      title: t("workflow.dataset"),
      page: "dataset",
      accent: "violet",
      badge: status.hasDataset ? t("common.ready") : t("common.notStarted"),
      badgeClass: status.hasDataset ? "success" : "muted",
      rows: [[t("workflow.images"), status.imageCount], [t("workflow.qualityCheck"), appState.currentProject?.dataset_health ? t("common.done") : t("common.notRun")]],
      progress: status.hasDataset ? 100 : 0,
      action: t("workflow.manageDataset"),
    },
    {
      step: 2,
      icon: "fa-pen-nib",
      title: t("workflow.annotation"),
      page: "labelme",
      accent: "green",
      badge: status.labelme.synced ? t("workflow.synced") : t("common.notStarted"),
      badgeClass: status.labelme.synced ? "success" : "muted",
      rows: [[t("workflow.annotated"), `${status.annotatedCount}/${status.imageCount}`], [t("workflow.coverage"), `${status.labelme.completionRate || 0}%`]],
      progress: status.labelme.completionRate || 0,
      action: t("workflow.openLabelMe"),
    },
    {
      step: 3,
      icon: "fa-robot",
      title: t("workflow.autoLabeling"),
      page: "auto-labeling",
      accent: "cyan",
      badge: t("common.notStarted"),
      badgeClass: "muted",
      rows: [[t("workflow.drafts"), 0], [t("workflow.models"), appState.models?.length || 0]],
      progress: 0,
      action: t("workflow.startAutoLabeling"),
    },
    {
      step: 4,
      icon: "fa-code-branch",
      title: t("workflow.split"),
      page: "split",
      accent: "orange",
      badge: status.splitComplete ? t("common.ready") : t("common.notReady"),
      badgeClass: status.splitComplete ? "success" : "danger",
      rows: [[t("workflow.trainValTest"), `${status.splitCounts.train || "-"} / ${status.splitCounts.val || "-"} / ${status.splitCounts.test || "-"}`], [t("workflow.splitFile"), status.splitComplete ? t("common.ready") : t("common.none")]],
      progress: status.splitComplete ? 100 : 0,
      action: t("workflow.createSplit"),
    },
    {
      step: 5,
      icon: "fa-wand-magic-sparkles",
      title: t("workflow.augmentation"),
      page: "augmentation",
      accent: "amber",
      badge: appState.currentProject?.augmentation_config ? t("workflow.configured") : t("common.notStarted"),
      badgeClass: appState.currentProject?.augmentation_config ? "success" : "muted",
      rows: [[t("workflow.policies"), appState.currentProject?.augmentation_config ? 1 : 0], [t("workflow.active"), appState.currentProject?.augmentation_config ? t("common.yes") : t("common.no")]],
      progress: appState.currentProject?.augmentation_config ? 100 : 0,
      action: t("workflow.configureAugmentation"),
    },
    {
      step: 6,
      icon: "fa-microchip",
      title: t("workflow.training"),
      page: "training",
      accent: "blue",
      badge: status.trainReady ? t("common.ready") : t("common.notStarted"),
      badgeClass: status.trainReady ? "success" : "muted",
      rows: [[t("workflow.runs"), appState.currentProject?.training_runs?.length || 0], [t("workflow.bestMap"), "--"]],
      progress: status.bestModelExists ? 100 : status.trainReady ? 60 : 0,
      action: t("workflow.startTraining"),
    },
    {
      step: 7,
      icon: "fa-chart-line",
      title: t("workflow.evaluation"),
      page: "evaluation",
      accent: "purple",
      badge: status.bestModelExists ? t("common.available") : t("common.notStarted"),
      badgeClass: status.bestModelExists ? "success" : "muted",
      rows: [[t("workflow.evaluations"), 0], [t("workflow.bestMap"), "--"]],
      progress: status.bestModelExists ? 70 : 0,
      action: t("workflow.runEvaluation"),
    },
    {
      step: 8,
      icon: "fa-flask",
      title: t("workflow.inferenceLab"),
      page: "inference",
      accent: "indigo",
      badge: appState.models?.length ? t("common.available") : t("common.notStarted"),
      badgeClass: appState.models?.length ? "success" : "muted",
      rows: [[t("workflow.models"), appState.models?.length || 0], [t("workflow.tests"), 0]],
      progress: appState.models?.length ? 50 : 0,
      action: t("workflow.openInferenceLab"),
    },
    {
      step: 9,
      icon: "fa-box-archive",
      title: t("workflow.export"),
      page: "export",
      accent: "teal",
      badge: status.bestModelExists ? t("common.ready") : t("common.notReady"),
      badgeClass: status.bestModelExists ? "success" : "danger",
      rows: [[t("workflow.exports"), 0], [t("workflow.lastExport"), "--"]],
      progress: status.bestModelExists ? 80 : 0,
      action: t("workflow.exportModel"),
    },
  ];

  setHTML("#control-cards", `
    ${renderCnnGuidedWizard(wizard)}
    <details class="workflow-map-panel workflow-map-details">
      <summary class="workflow-map-summary">
        <span><i class="fa-solid fa-map"></i> ${escapeHtml(t("workflow.detailsSummary"))}</span>
        <small>${escapeHtml(t("workflow.detailsHint"))}</small>
      </summary>
      <div class="section-title workflow-map-title">
        <div>
          <h2><i class="fa-solid fa-map"></i> ${escapeHtml(t("workflow.detailsTitle"))}</h2>
          <p>${escapeHtml(t("workflow.detailsSubtitle"))}</p>
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
