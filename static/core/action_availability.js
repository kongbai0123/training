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
    el.disabled = !rules[requirement];
    el.classList.toggle("btn-disabled", !rules[requirement]);
  });

  const startBtn = qs("#btn-start-train");
  if (startBtn) {
    startBtn.disabled = !status.trainReady;
    startBtn.classList.toggle("btn-disabled", !status.trainReady);
  }
}
