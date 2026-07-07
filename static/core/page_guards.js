import { qs, setHTML, setText, escapeHtml } from "../utils.js";
import { isRnnTrainingWorkspaceActive } from "../pages/training_modes.js?v=20260706-rnn-pc-catalog";

export function renderPageGuards(pageId, status) {
  if (isRnnTrainingWorkspaceActive(pageId)) {
    const container = qs("#page-guards-container");
    const section = qs("#section-page-guards");
    if (container && section) {
      section.style.display = "none";
      setHTML("#page-guards-container", "");
    }
    return;
  }

  const guards = {
    dataset: [],
    labelme: [],
    split: [],
    augmentation: [],
    training: [],
    evaluation: [],
    "auto-labeling": [],
    export: []
  };

  if (!status.hasProject) {
    const guard = statusGuard("warning", "No project opened", ["This page is available, but actions are disabled."], "Open Projects or Browse History to choose a project.");
    Object.keys(guards).forEach((key) => guards[key].push(guard));
  }
  if (status.hasProject && !status.hasDataset) {
    guards.labelme.push(statusGuard("warning", "Dataset missing", ["Images folder is empty."], "Import images from Dataset first."));
    guards.split.push(statusGuard("warning", "Dataset missing", ["Train / Val / Test cannot be created yet."], "Import images from Dataset first."));
    guards.training.push(statusGuard("danger", "Training blocked", ["Dataset is missing."], "Import images from Dataset first."));
  }
  if (status.hasDataset && !status.labelme.synced) {
    guards.training.push(statusGuard("danger", "Training blocked", ["LabelMe annotations are not synced."], "Open LabelMe and sync annotations before training."));
    guards.split.push(statusGuard("info", "LabelMe pending", ["Split can be configured after LabelMe JSON is ready."], "Open LabelMe and sync annotations first."));
  }
  if (status.hasDataset && !status.splitComplete) {
    guards.training.push(statusGuard("danger", "Training blocked", ["Train / Val / Test split is missing."], "Create a split before training."));
    guards.augmentation.push(statusGuard("warning", "Split required", ["Augmentation requires a target train split."], "Create a Train / Val / Test split first."));
  }
  if (!status.bestModelExists) {
    guards.evaluation.push(statusGuard("warning", "No trained model", ["No best model is available yet."], "Finish training before reviewing mAP / IoU."));
    guards.export.push(statusGuard("warning", "No exportable model", ["No trained model is available for export."], "Finish training before exporting PT / ONNX."));
  }

  const activeGuards = guards[pageId] || [];
  const container = qs("#page-guards-container");
  const section = qs("#section-page-guards");

  if (container && section) {
    if (activeGuards.length > 0) {
      section.style.display = "block";
      setHTML("#page-guards-container", activeGuards.join(""));
      const pageTitleMap = {
        dataset: "Dataset Page Status",
        labelme: "LabelMe Page Status",
        split: "Split Page Status",
        augmentation: "Augmentation Status",
        training: "Training Status",
        evaluation: "Evaluation Status",
        export: "Export Status"
      };
      setText("#page-guards-title", pageTitleMap[pageId] || "Page Status");
    } else {
      section.style.display = "none";
      setHTML("#page-guards-container", "");
    }
  }
}

function statusGuard(type, title, items, nextAction) {
  return `
    <div class="status-guard ${type}">
      <div class="guard-title">${escapeHtml(title)}</div>
      <ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      <div class="guard-next-actions">${escapeHtml(nextAction)}</div>
    </div>
  `;
}
