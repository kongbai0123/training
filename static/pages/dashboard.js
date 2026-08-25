import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { qs, setHTML, escapeHtml } from "../utils.js";
import { getDirtyFormSummaries } from "../core/dirty_forms.js";
import { getStaleResources } from "../core/resource_freshness.js";

export const OVERVIEW_MODULES = Object.freeze([
  Object.freeze({ mode: "rnn", icon: "fa-chart-line", titleKey: "dashboard.module.rnn.title", descriptionKey: "dashboard.module.rnn.description", capabilityKey: "dashboard.module.rnn.capabilities" }),
  Object.freeze({ mode: "cnn", icon: "fa-images", titleKey: "dashboard.module.cnn.title", descriptionKey: "dashboard.module.cnn.description", capabilityKey: "dashboard.module.cnn.capabilities" }),
  Object.freeze({ mode: "tabular", icon: "fa-table-columns", titleKey: "dashboard.module.tabular.title", descriptionKey: "dashboard.module.tabular.description", capabilityKey: "dashboard.module.tabular.capabilities" }),
]);

export function initDashboard() {
  qs("#btn-dashboard-refresh")?.addEventListener("click", () => eventBus.emit("refresh-project"));
  qs("#overview-module-grid")?.addEventListener("click", (event) => {
    const target = event.target.closest("[data-overview-module]");
    if (!target) return;
    event.preventDefault();
    eventBus.emit("open-training-module", target.dataset.overviewModule);
  });
}

export function renderDashboard(status) {
  renderDashboardAlerts();
  renderOverviewModules();
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
        <strong>${escapeHtml(t("dashboard.alert.unsaved"))}</strong>
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

function renderOverviewModules() {
  const activeProject = appState.currentProject;
  const activeMode = resolveProjectMode(activeProject);
  const counts = countProjectsByMode(appState.projects || []);
  const cards = OVERVIEW_MODULES.map((module) => {
    const isActiveProject = Boolean(activeProject && activeMode === module.mode);
    const context = isActiveProject
      ? t("dashboard.module.activeProject", { name: activeProject.project_name || activeProject.project_id || "--" })
      : t("dashboard.module.projectCount", { count: counts[module.mode] || 0 });
    return `
      <article class="overview-module-card overview-module-${module.mode}" data-module-card="${module.mode}">
        <header>
          <span class="overview-module-icon" aria-hidden="true"><i class="fa-solid ${module.icon}"></i></span>
          <div>
            <h3>${escapeHtml(t(module.titleKey))}</h3>
            <span class="overview-module-context no-i18n${isActiveProject ? " is-active" : ""}">${escapeHtml(context)}</span>
          </div>
        </header>
        <p>${escapeHtml(t(module.descriptionKey))}</p>
        <div class="overview-module-capabilities">${escapeHtml(t(module.capabilityKey))}</div>
        <button type="button" class="btn btn-primary" data-overview-module="${module.mode}" aria-label="${escapeHtml(t("dashboard.module.openAria", { module: t(module.titleKey) }))}">
          <span>${escapeHtml(t("dashboard.module.open"))}</span>
          <i class="fa-solid fa-arrow-right" aria-hidden="true"></i>
        </button>
      </article>
    `;
  });
  setHTML("#overview-module-grid", cards.join(""));
}

function countProjectsByMode(projects) {
  return projects.reduce((counts, project) => {
    counts[resolveProjectMode(project)] += 1;
    return counts;
  }, { cnn: 0, rnn: 0, tabular: 0 });
}

function resolveProjectMode(project) {
  const explicit = String(project?.architecture || project?.training_mode || project?.training_config?.architecture || "").toLowerCase();
  if (explicit === "tabular") return "tabular";
  if (explicit === "rnn") return "rnn";
  const taskType = String(project?.task_type || project?.task || "").toLowerCase();
  if (taskType.includes("tabular")) return "tabular";
  return ["sequence", "time_series", "timeseries", "rnn"].some((token) => taskType.includes(token)) ? "rnn" : "cnn";
}

function renderRecentProjects(projects) {
  eventBus.emit("render-recent-projects-list", (projects || []).slice(0, 3));
}

function renderActivity(status) {
  const key = !status.hasProject
    ? "dashboard.activity.noProject"
    : !status.hasDataset
      ? "dashboard.activity.noDataset"
      : !status.splitComplete
        ? "dashboard.activity.noSplit"
        : !status.trainReady
          ? "dashboard.activity.notReady"
          : "dashboard.activity.ready";
  setHTML("#recent-activity-list", `<div class="activity-item">${escapeHtml(t(key))}</div>`);
}
