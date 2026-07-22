import { eventBus } from "./event_bus.js";
import { translate as translateI18n, applyLanguageToDocument } from "./state/i18n.js";

export const appState = {
  currentPage: "dashboard",
  dashboardFocus: "overview",
  currentProjectId: null,
  currentProject: null,
  projects: [],
  datasetVisibleLimit: 80,
  newProjectClasses: [],
  pendingDeleteProjectId: null,
  trainingStatus: null,
  models: [],
  inferenceModels: [],
  inferenceJobs: [],
  inferenceJobsProjectId: "",
  inferenceJobsLoading: false,
  inferenceLastResult: null,
  inferenceRunning: false,
  inferenceSelectedModelId: "",
  latestAnnotationImport: null,
  wsConn: null,
  bootstrap: {
    token: localStorage.getItem("vts-session-token") || "",
    startedAt: "",
    expiresAt: "",
    version: "",
    environment: ""
  },
  settings: {
    theme: localStorage.getItem("vts-theme") || "dark",
    language: localStorage.getItem("vts-language") || "zh-TW"
  },
  labelme: {
    uiReady: true,
    backendReady: true,
    synced: false,
    totalImages: 0,
    jsonCount: 0,
    missingJson: 0,
    emptyJson: 0,
    unknownLabels: 0,
    invalidJson: 0,
    completionRate: 0
  }
};

export { i18n } from "./state/i18n.js";

export function t(key, params = {}) {
  return translateI18n(key, appState.settings.language, params);
}

export const augmentationPresets = {
  clear_day: {
    overcast: 0,
    sunSuppression: 0,
    brightness: 0.1,
    contrast: 0.1,
    shadow: false,
    rain: 0,
    fog: 0,
    wetSurface: 0,
    puddle: 0,
    splash: 0,
    lensDroplets: 0,
    motionBlur: 0,
    noise: 0,
    perspective: 0
  },
  low_light: {
    overcast: 0,
    sunSuppression: 0,
    brightness: -0.25,
    contrast: 0.15,
    shadow: true,
    rain: 0,
    fog: 0,
    wetSurface: 0, puddle: 0, splash: 0, lensDroplets: 0,
    motionBlur: 0,
    noise: 0.05,
    perspective: 0
  },
  rainy: {
    overcast: 0.6,
    sunSuppression: 0.75,
    brightness: 0,
    contrast: 0,
    shadow: false,
    rain: 0.55,
    fog: 0.3,
    wetSurface: 0,
    puddle: 0,
    splash: 0,
    lensDroplets: 0,
    motionBlur: 0,
    noise: 0,
    perspective: 0
  },
  foggy: {
    overcast: 0.45,
    sunSuppression: 0.5,
    brightness: 0.05,
    contrast: -0.15,
    shadow: false,
    rain: 0,
    fog: 0.4,
    wetSurface: 0, puddle: 0, splash: 0, lensDroplets: 0,
    motionBlur: 0,
    noise: 0,
    perspective: 0
  },
  motion_camera: {
    overcast: 0,
    sunSuppression: 0,
    brightness: 0,
    contrast: 0,
    shadow: false,
    rain: 0,
    fog: 0,
    wetSurface: 0, puddle: 0, splash: 0, lensDroplets: 0,
    motionBlur: 0.35,
    noise: 0.08,
    perspective: 0
  },
  strong_shadow: {
    overcast: 0,
    sunSuppression: 0,
    brightness: -0.12,
    contrast: 0.18,
    shadow: true,
    rain: 0,
    fog: 0,
    wetSurface: 0, puddle: 0, splash: 0, lensDroplets: 0,
    motionBlur: 0,
    noise: 0.03,
    perspective: 0
  },
  wet_reflection: {
    overcast: 0.78,
    sunSuppression: 0.82,
    brightness: 0,
    contrast: 0,
    shadow: false,
    rain: 0.58,
    fog: 0.28,
    wetSurface: 0.85,
    puddle: 0.4,
    splash: 0.38,
    lensDroplets: 0,
    motionBlur: 0,
    noise: 0,
    perspective: 0
  },
  lens_rain: {
    overcast: 0,
    sunSuppression: 0,
    brightness: 0,
    contrast: 0,
    shadow: false,
    rain: 0,
    fog: 0,
    wetSurface: 0,
    puddle: 0,
    splash: 0,
    lensDroplets: 0.45,
    motionBlur: 0,
    noise: 0,
    perspective: 0
  },
  night_road: {
    overcast: 0,
    sunSuppression: 0,
    brightness: -0.35,
    contrast: 0.22,
    shadow: true,
    rain: 0,
    fog: 0.08,
    wetSurface: 0, puddle: 0, splash: 0, lensDroplets: 0,
    motionBlur: 0.08,
    noise: 0.12,
    perspective: 0
  },
  suburban_mix: {
    overcast: 0.15,
    sunSuppression: 0.15,
    brightness: 0.04,
    contrast: 0.08,
    shadow: true,
    rain: 0.08,
    fog: 0.04,
    wetSurface: 0, puddle: 0, splash: 0, lensDroplets: 0,
    motionBlur: 0.04,
    noise: 0.04,
    perspective: 0
  },
  forest_road: {
    overcast: 0.1,
    sunSuppression: 0.1,
    brightness: -0.08,
    contrast: 0.16,
    shadow: true,
    rain: 0,
    fog: 0.06,
    wetSurface: 0, puddle: 0, splash: 0, lensDroplets: 0,
    motionBlur: 0.03,
    noise: 0.04,
    perspective: 0
  },
  generalization: {
    overcast: 0.2,
    sunSuppression: 0.2,
    brightness: 0.08,
    contrast: 0.08,
    shadow: true,
    rain: 0.12,
    fog: 0.1,
    wetSurface: 0.08,
    puddle: 0.02,
    splash: 0,
    lensDroplets: 0,
    motionBlur: 0.12,
    noise: 0.06,
    perspective: 0
  }
};

export const fixedAugmentationValues = {
  brightness: 0.2,
  contrast: 0.2,
  rain: 0.4,
  fog: 0.4,
  motionBlur: 0.3,
  noise: 0.08,
  perspective: 0.06
};

export function initPreferences() {
  applyTheme(appState.settings.theme);
  applyLanguage(appState.settings.language);
}

export function applyTheme(theme) {
  const nextTheme = theme === "light" ? "light" : "dark";
  appState.settings.theme = nextTheme;
  localStorage.setItem("vts-theme", nextTheme);
  document.body.dataset.theme = nextTheme;

  const themeSelect = document.querySelector("#settings-theme");
  if (themeSelect) themeSelect.value = nextTheme;

  const icon = document.querySelector("#btn-theme-toggle i");
  if (icon) {
    icon.className = nextTheme === "dark" ? "fa-solid fa-sun" : "fa-solid fa-moon";
  }
  applyLanguage(appState.settings.language);
}

export function applyLanguage(language, options = {}) {
  const nextLanguage = language === "en" ? "en" : "zh-TW";
  appState.settings.language = nextLanguage;
  localStorage.setItem("vts-language", nextLanguage);
  applyLanguageToDocument({
    language: nextLanguage,
    theme: appState.settings.theme,
    translate: t,
  });
  if (options.emit !== false) {
    eventBus.emit("language-changed", nextLanguage);
  }
}

export function updateLabelMeState() {
  const project = appState.currentProject;
  if (!project) return;
  const rawImages = (project.images || []).filter((img) => !img.is_augmented);
  const total = rawImages.length;

  const annotated = rawImages.filter((img) => img.status === "annotated").length;
  const flagged = rawImages.filter((img) => img.status === "flagged").length;
  const skipped = rawImages.filter((img) => img.status === "skipped").length;

  const missing = total - annotated - flagged - skipped;
  const hasAnnotated = annotated > 0;

  appState.labelme = {
    uiReady: true,
    backendReady: true,
    synced: hasAnnotated || appState.labelme.synced,
    totalImages: total,
    jsonCount: annotated,
    missingJson: missing,
    emptyJson: 0,
    unknownLabels: appState.labelme.unknownClasses ? appState.labelme.unknownClasses.length : 0,
    invalidJson: 0,
    completionRate: total > 0 ? Math.round((annotated / total) * 100) : 0
  };
}

export function getProjectStatus(project) {
  const images = project?.images || [];
  const rawImages = images.filter((img) => !img.is_augmented);
  const annotatedCount = rawImages.filter((img) => img.status === "annotated").length;
  const flaggedCount = rawImages.filter((img) => img.status === "flagged").length;
  const skippedCount = rawImages.filter((img) => img.status === "skipped").length;
  const splitCounts = rawImages.reduce((acc, img) => {
    if (img.split) acc[img.split] = (acc[img.split] || 0) + 1;
    return acc;
  }, { train: 0, val: 0, test: 0 });
  const splitComplete = splitCounts.train > 0 && splitCounts.val > 0;
  const training = appState.trainingStatus || {};
  const trainingLabel = training.status || "idle";
  const bestModelExists = Boolean(training.best_model || project?.best_model);
  const labelme = appState.labelme;
  const autoLabelReviewGate = project?.auto_label_review_gate || { blocked: false, pending: 0 };
  const blockers = [];
  if (!project) blockers.push(t("status.blocker.noProject"));
  if (project && rawImages.length === 0) blockers.push(t("status.blocker.noImages"));
  if (project && !labelme.synced) blockers.push(t("status.blocker.labelmeNotSynced"));
  if (project && !splitComplete) blockers.push(t("status.blocker.splitIncomplete"));
  if (project && autoLabelReviewGate.blocked) blockers.push(t("status.blocker.autoLabelReview"));
  const trainReady = Boolean(project && rawImages.length > 0 && labelme.synced && splitComplete && !autoLabelReviewGate.blocked);

  return {
    hasProject: Boolean(project),
    projectName: project?.project_name || t("common.noProjectOpened"),
    taskType: project?.task_type || "--",
    classNames: project?.class_names || [],
    datasetPath: project?.dataset_path || "",
    imageCount: rawImages.length,
    annotatedCount,
    flaggedCount,
    skippedCount,
    unannotatedCount: Math.max(0, rawImages.length - annotatedCount - flaggedCount - skippedCount),
    annotationRate: rawImages.length ? Math.round((annotatedCount / rawImages.length) * 100) : 0,
    hasDataset: rawImages.length > 0,
    splitCounts,
    splitComplete,
    splitQuality: project?.split_config?.split_quality_score || project?.split_report?.score || 0,
    trainingLabel,
    trainingRunning: trainingLabel === "training",
    bestModelExists,
    trainReady,
    blockers,
    labelme,
    autoLabelReviewGate
  };
}
