import { qs, qsa } from "../utils.js";

export function updateActionAvailability(status) {
  const rules = {
    project: status.hasProject,
    dataset: status.hasDataset,
    split: status.splitComplete,
    "train-ready": status.trainReady
  };

  qsa(".guarded").forEach((el) => {
    const requirement = el.dataset.requires;
    if (!requirement) return;
    const blocked = !rules[requirement];
    el.disabled = false;
    el.dataset.readinessBlocked = blocked ? "true" : "false";
    el.setAttribute("aria-disabled", blocked ? "true" : "false");
    el.classList.toggle("is-readiness-blocked", blocked);
  });

  const startBtn = qs("#btn-start-train");
  if (startBtn) {
    const blocked = !status.trainReady;
    startBtn.disabled = false;
    startBtn.dataset.requires = "train-ready";
    startBtn.dataset.readinessBlocked = blocked ? "true" : "false";
    startBtn.setAttribute("aria-disabled", blocked ? "true" : "false");
    startBtn.classList.toggle("is-readiness-blocked", blocked);
  }
}
