import { initDashboard, renderDashboard } from "../pages/dashboard.js?v=20260710-training-i18n-ux";
import { initProjectAssistant, renderProjectAssistantPage } from "../pages/project_assistant.js?v=20260710-project-assistant";
import { initProjects, renderProjectsPage } from "../pages/projects.js?v=20260709-project-open-delegation";
import { initDataset, renderDatasetPage } from "../pages/dataset.js?v=20260630-progress-hud";
import { initLabelMe, renderLabelMeManager } from "../pages/labelme.js?v=20260711-layout-export-precision";
import { initSplit, renderSplitPage } from "../pages/split.js";
import { initAugmentation, renderAugmentationPage } from "../pages/augmentation.js?v=20260711-layout-export-precision";
import { initTraining, renderTrainingMonitor, loadRecommendedConfig } from "../pages/training.js?v=20260702-cnn-eval-polish2";
import {
  initTrainingModeSidebar,
  renderTrainingModeSidebar,
  renderTrainingWorkspace,
  syncTrainingModeForProject,
} from "../pages/training_modes.js?v=20260709-export-artifacts";
import { initEvaluation, renderEvaluationPage } from "../pages/evaluation.js?v=20260702-cnn-eval-polish2";
import { initModelCompare, renderModelComparePage } from "../pages/model_compare.js?v=20260708-compare-scope-artifacts";
import { initInference, renderInferencePage } from "../pages/inference.js?v=20260702-model-scroll-bounds";
import { initAutoLabeling, renderAutoLabelingPage } from "../pages/auto_labeling.js?v=20260709-review-gate";
import { initExport, renderExportPage } from "../pages/export.js?v=20260711-layout-export-precision";
import { initSettings, renderSettingsPage } from "../pages/settings.js";

export function initPageModules() {
  initDashboard();
  initProjectAssistant();
  initProjects();
  initDataset();
  initLabelMe();
  initSplit();
  initAugmentation();
  initTraining();
  initEvaluation();
  initModelCompare();
  initInference();
  initAutoLabeling();
  initExport();
  initSettings();
  initTrainingModeSidebar();
}

export function renderPrimaryPageModules(status) {
  renderDashboard(status);
}

export function renderSecondaryPageModules(status) {
  renderDatasetPage(status);
  renderLabelMeManager(status);
  renderSplitPage(status);
  renderAugmentationPage(status);
  renderTrainingMonitor();
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
  renderEvaluationPage(status);
  renderModelComparePage();
  renderInferencePage(status);
  renderAutoLabelingPage(status);
  renderExportPage(status);
  renderSettingsPage();
  renderProjectAssistantPage();
  renderProjectsPage();
}

export function syncPageModeForProject(project, pageId) {
  syncTrainingModeForProject(project, pageId);
}

export function loadPageRecommendedConfig() {
  return loadRecommendedConfig();
}
