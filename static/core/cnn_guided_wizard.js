import { escapeHtml } from "../utils.js";

export function buildCnnGuidedWizard(status = {}, appState = {}) {
  const hasProject = Boolean(status.hasProject);
  const steps = [
    {
      id: "project",
      title: "Project",
      page: "projects",
      complete: hasProject,
      blocker: "Create or open a project.",
      action: "Create / Open"
    },
    {
      id: "dataset",
      title: "Dataset",
      page: "dataset",
      complete: Boolean(status.hasDataset),
      blocker: "Import images or a dataset ZIP.",
      action: "Import Dataset"
    },
    {
      id: "annotation",
      title: "Annotation",
      page: "labelme",
      complete: Boolean(status.labelme?.synced),
      blocker: "Sync or review LabelMe annotations.",
      action: "Open LabelMe"
    },
    {
      id: "split",
      title: "Split",
      page: "split",
      complete: Boolean(status.splitComplete),
      blocker: "Create train / validation / test split.",
      action: "Create Split"
    },
    {
      id: "training",
      title: "Training",
      page: "training",
      complete: Boolean(status.trainReady || appState.trainingStatus?.status === "completed"),
      blocker: "Review training config and start a run.",
      action: "Open Training"
    },
    {
      id: "decision",
      title: "Evaluate",
      page: "model-compare",
      complete: Boolean(status.bestModelExists),
      blocker: "Compare completed runs before export.",
      action: "Compare Runs"
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
          <h2><i class="fa-solid fa-route"></i> CNN Guided Wizard</h2>
          <p>Practical path from project setup to deployment decision. Next action is always routed to the real page.</p>
        </div>
        <span class="summary-badge badge-neutral">${escapeHtml(wizard.completed)} / ${escapeHtml(wizard.total)}</span>
      </div>
      <div class="progress-block">
        <div class="progress-track"><div class="progress-fill" style="width:${escapeHtml(wizard.percent)}%"></div></div>
        <div class="progress-row"><span>Workflow progress</span><strong>${escapeHtml(wizard.percent)}%</strong></div>
      </div>
      <div class="guided-step-grid">
        ${wizard.steps.map((step, index) => `
          <article class="guided-step ${step.complete ? "is-complete" : step.id === wizard.nextStep.id ? "is-next" : ""}">
            <span>${index + 1}</span>
            <div>
              <strong>${escapeHtml(step.title)}</strong>
              <small>${escapeHtml(step.complete ? "Ready" : step.blocker)}</small>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" data-nav="${escapeHtml(step.page)}">${escapeHtml(step.action)}</button>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}
