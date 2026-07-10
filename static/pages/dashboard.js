import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { qs, setHTML, escapeHtml } from "../utils.js";
import { getDirtyFormSummaries } from "../core/dirty_forms.js";
import { getStaleResources } from "../core/resource_freshness.js";
import { renderTrainingFlowGuide } from "../core/training_flow_guide.js";
import { trainingModeState } from "./training_mode_state.js";
import {
  buildProjectStatusView,
  renderProjectStatusStrip,
  resolveDashboardProjectMode,
} from "../core/project_status_strip.js";

export function initDashboard() {
  qs("#btn-dashboard-refresh")?.addEventListener("click", () => {
    eventBus.emit("refresh-project");
  });
  qs("#control-cards")?.addEventListener("click", (event) => {
    const target = event.target.closest("[data-rnn-target]");
    if (!target) return;
    event.preventDefault();
    const panel = target.dataset.rnnTarget;
    qs(`#rnn-mode-nav [data-rnn-nav="${panel}"]`)?.click();
  });
}

export function renderDashboard(status) {
  setHTML("#dashboard-kpis", "");
  renderDashboardAlerts();
  renderTrainingFlow(status);
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

function renderTrainingFlow(status) {
  const project = appState.currentProject;
  const mode = resolveDashboardProjectMode(project);
  const statusView = buildProjectStatusView({
    status,
    project,
    models: appState.models,
    rnnState: trainingModeState.rnn,
  });
  setHTML("#control-cards", `
    ${renderTrainingFlowGuide({ mode })}
    ${renderProjectStatusStrip(statusView)}
  `);
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
