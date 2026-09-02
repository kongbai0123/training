import { initDashboard, renderDashboard } from "../pages/dashboard.js?v=20260825-tabular-mvp";
import { initProjectAssistant, renderProjectAssistantPage } from "../pages/project_assistant.js?v=20260825-tabular-mvp";
import { initProjects, renderProjectsPage } from "../pages/projects.js?v=20260825-tabular-mvp";
import { initDataset, renderDatasetPage } from "../pages/dataset.js?v=20260630-progress-hud";
import { initLabelMe, renderLabelMeManager } from "../pages/labelme.js?v=20260711-layout-export-precision";
import { initSplit, renderSplitPage } from "../pages/split.js";
import { initAugmentation, renderAugmentationPage } from "../pages/augmentation.js?v=20260722-augmentation-compare2";
import { initTraining, renderTrainingMonitor, loadRecommendedConfig } from "../pages/training.js?v=20260722-run-restore-history-count";
import {
  initTrainingModeSidebar,
  renderTrainingModeSidebar,
  renderTrainingWorkspace,
  resolveProjectWorkspacePage,
  syncTrainingModeForProject,
} from "../pages/training_modes.js?v=20260902-unified-evaluation";
import { initEvaluation, renderEvaluationPage } from "../pages/evaluation.js?v=20260902-unified-evaluation";
import { initModelCompare, renderModelComparePage } from "../pages/model_compare.js?v=20260825-tabular-mvp";
import { initInference, renderInferencePage } from "../pages/inference.js?v=20260702-model-scroll-bounds";
import { initAutoLabeling, renderAutoLabelingPage } from "../pages/auto_labeling.js?v=20260709-review-gate";
import { initExport, renderExportPage } from "../pages/export.js?v=20260711-layout-export-precision";
import { initSettings, renderSettingsPage } from "../pages/settings.js";
import { initModelGuide, renderModelGuidePage } from "../pages/model_guide.js?v=20260724-model-guide-controls2";
import { initTabularWorkspace, renderTabularWorkspace } from "../pages/tabular.js?v=20260825-tabular-mvp";
import { appState } from "../state.js";

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
  initModelGuide();
  initTabularWorkspace();
  initTrainingModeSidebar();
}

export function renderPrimaryPageModules(status) {
  renderDashboard(status);
}

export function renderSecondaryPageModules(status) {
  renderTrainingModeSidebar();
  const renderActivePage = {
    dataset: () => renderDatasetPage(status),
    labelme: () => renderLabelMeManager(status),
    split: () => renderSplitPage(status),
    augmentation: () => renderAugmentationPage(status),
    training: () => {
      renderTrainingMonitor();
      renderTrainingWorkspace();
    },
    tabular: () => renderTabularWorkspace(status),
    evaluation: () => renderEvaluationPage(status),
    "model-compare": () => renderModelComparePage(),
    inference: () => renderInferencePage(status),
    "auto-labeling": () => renderAutoLabelingPage(status),
    export: () => renderExportPage(status),
    settings: () => renderSettingsPage(),
    "model-guide": () => renderModelGuidePage(),
    projects: () => renderProjectsPage(),
    history: () => renderProjectsPage(),
  }[appState.currentPage];
  renderActivePage?.();
  renderProjectAssistantPage();
}

export function syncPageModeForProject(project, pageId) {
  syncTrainingModeForProject(project, pageId);
}

export function resolvePageForProject(project, pageId) {
  return resolveProjectWorkspacePage(project, pageId);
}

export function loadPageRecommendedConfig() {
  return loadRecommendedConfig();
}
