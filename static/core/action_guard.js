import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { qs, escapeHtml } from "../utils.js";

const REQUIREMENTS = {
  project: { valid: (s) => s.hasProject, reasons: () => [t("actionGuard.reason.project")], actions: [["history", "actionGuard.openHistory"], ["projects", "actionGuard.newProject"]] },
  dataset: { valid: (s) => s.hasDataset, reasons: () => [t("actionGuard.reason.dataset")], actions: [["dataset", "actionGuard.openDataset"]] },
  split: { valid: (s) => s.splitComplete, reasons: () => [t("actionGuard.reason.split")], actions: [["split", "actionGuard.openSplit"]] },
  "train-ready": {
    valid: (s) => s.trainReady,
    reasons: (s) => s.blockers?.length ? s.blockers : [t("actionGuard.reason.training")],
    actions: [["dataset", "actionGuard.openDataset"], ["labelme", "actionGuard.openLabelMe"], ["split", "actionGuard.openSplit"]]
  }
};

export function initActionGuard() {
  document.addEventListener("click", interceptGuardedAction, true);
  qs("#btn-close-action-guard")?.addEventListener("click", closeActionGuard);
  qs("#action-guard-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "action-guard-modal") closeActionGuard();
  });
  qs("#action-guard-actions")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action-guard-nav]");
    if (!button) return;
    closeActionGuard();
    if (button.dataset.actionGuardNav === "projects") eventBus.emit("open-create-project-modal");
    else eventBus.emit("navigate", button.dataset.actionGuardNav);
  });
}

export function evaluateActionRequirement(requirement, project = appState.currentProject) {
  const rule = REQUIREMENTS[requirement];
  if (!rule) return { allowed: true, reasons: [], actions: [] };
  const status = getProjectStatus(project);
  return { allowed: Boolean(rule.valid(status)), reasons: rule.reasons(status), actions: rule.actions };
}

function interceptGuardedAction(event) {
  const target = event.target.closest(".guarded, [data-requires]");
  if (!target) return;
  const customReason = target.dataset.blockReason?.trim();
  const result = customReason
    ? { allowed: false, reasons: [customReason], actions: [] }
    : evaluateActionRequirement(target.dataset.requires);
  if (result.allowed) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  openActionGuard({ title: target.dataset.actionTitle || target.textContent.trim() || t("actionGuard.defaultAction"), ...result });
}

export function openActionGuard({ title, reasons = [], actions = [] }) {
  const modal = qs("#action-guard-modal");
  if (!modal) return;
  qs("#action-guard-operation").textContent = title;
  qs("#action-guard-reasons").innerHTML = reasons
    .map((reason) => typeof reason === "object" && reason ? reason.text : reason)
    .filter(Boolean)
    .map((reason) => `<li>${escapeHtml(String(reason))}</li>`)
    .join("");
  qs("#action-guard-actions").innerHTML = actions.map(([page, label]) => `<button type="button" class="btn btn-secondary" data-action-guard-nav="${escapeHtml(page)}">${escapeHtml(t(label))}</button>`).join("");
  modal.hidden = false;
}

function closeActionGuard() {
  const modal = qs("#action-guard-modal");
  if (modal) modal.hidden = true;
}
