import { escapeHtml } from "../utils.js";
import { t } from "../state.js";

export function buildCnnGuidedWizard(status = {}, appState = {}) {
  const hasProject = Boolean(status.hasProject);
  const steps = [
    {
      id: "project",
      title: t("guided.project"),
      page: "projects",
      complete: hasProject,
      blocker: t("guided.projectBlocker"),
      action: t("guided.projectAction")
    },
    {
      id: "dataset",
      title: t("guided.dataset"),
      page: "dataset",
      complete: Boolean(status.hasDataset),
      blocker: t("guided.datasetBlocker"),
      action: t("guided.datasetAction")
    },
    {
      id: "annotation",
      title: t("guided.annotation"),
      page: "labelme",
      complete: Boolean(status.labelme?.synced),
      blocker: t("guided.annotationBlocker"),
      action: t("guided.annotationAction")
    },
    {
      id: "split",
      title: t("guided.split"),
      page: "split",
      complete: Boolean(status.splitComplete),
      blocker: t("guided.splitBlocker"),
      action: t("guided.splitAction")
    },
    {
      id: "training",
      title: t("guided.training"),
      page: "training",
      complete: Boolean(status.trainReady || appState.trainingStatus?.status === "completed"),
      blocker: t("guided.trainingBlocker"),
      action: t("guided.trainingAction")
    },
    {
      id: "decision",
      title: t("guided.evaluate"),
      page: "model-compare",
      complete: Boolean(status.bestModelExists),
      blocker: t("guided.evaluateBlocker"),
      action: t("guided.evaluateAction")
    }
  ];
  const nextStep = steps.find((step) => !step.complete) || steps[steps.length - 1];
  const completed = steps.filter((step) => step.complete).length;
  return {
    steps,
    nextStep,
    completed,
    total: steps.length,
    percent: Math.round((completed / steps.length) * 100)
  };
}

export function renderCnnGuidedWizard(wizard) {
  if (!wizard) return "";
  return `
    <section class="cnn-guided-wizard" data-ui-smoke="cnn-guided-wizard">
      <div class="section-title workflow-map-title">
        <div>
          <h2><i class="fa-solid fa-route"></i> ${escapeHtml(t("guided.title"))}</h2>
          <p>${escapeHtml(t("guided.subtitle"))}</p>
        </div>
        <span class="summary-badge badge-neutral">${escapeHtml(wizard.completed)} / ${escapeHtml(wizard.total)}</span>
      </div>
      <div class="progress-block">
        <div class="progress-track"><div class="progress-fill" style="width:${escapeHtml(wizard.percent)}%"></div></div>
        <div class="progress-row"><span>${escapeHtml(t("guided.progress"))}</span><strong>${escapeHtml(wizard.percent)}%</strong></div>
      </div>
      <div class="guided-step-grid">
        ${wizard.steps.map((step, index) => `
          <article class="guided-step ${step.complete ? "is-complete" : step.id === wizard.nextStep.id ? "is-next" : ""}">
            <span>${index + 1}</span>
            <div>
              <strong>${escapeHtml(step.title)}</strong>
              <small>${escapeHtml(step.complete ? t("common.ready") : step.blocker)}</small>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" data-nav="${escapeHtml(step.page)}">${escapeHtml(step.action)}</button>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}
