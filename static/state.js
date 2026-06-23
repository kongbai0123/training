import { eventBus } from "./event_bus.js";

export const appState = {
  currentPage: "dashboard",
  currentProjectId: null,
  currentProject: null,
  projects: [],
  datasetVisibleLimit: 80,
  newProjectClasses: [],
  pendingDeleteProjectId: null,
  trainingStatus: null,
  models: [],
  inferenceModels: [],
  inferenceLastResult: null,
  inferenceRunning: false,
  inferenceSelectedModelId: "",
  wsConn: null,
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

export const i18n = {
  "zh-TW": {
    themeToggle: "明亮",
    themeToggleDark: "深色",
    browseHistory: "瀏覽歷史",
    navDashboard: "總覽",
    navProjects: "專案",
    navDataset: "資料集",
    navLabelMe: "LabelMe",
    navSplit: "資料分散",
    navAugmentation: "物理擴充",
    navTraining: "模型訓練",
    navEvaluation: "評估",
    navInference: "模型測試",
    navExport: "匯出",
    navHistory: "歷史紀錄",
    navSettings: "設定",
    settingsTitle: "設定",
    settingsSubtitle: "可即時切換語言與背景明亮度，設定會保存在此瀏覽器。",
    preferencesTitle: "偏好設定",
    languageLabel: "語言",
    themeLabel: "背景明亮度",
    systemTitle: "系統狀態"
  },
  en: {
    themeToggle: "Light",
    themeToggleDark: "Dark",
    browseHistory: "Browse History",
    navDashboard: "Dashboard",
    navProjects: "Projects",
    navDataset: "Dataset",
    navLabelMe: "LabelMe",
    navSplit: "Split",
    navAugmentation: "Augmentation",
    navTraining: "Training",
    navEvaluation: "Evaluation",
    navInference: "Inference Lab",
    navExport: "Export",
    navHistory: "History",
    navSettings: "Settings",
    settingsTitle: "Settings",
    settingsSubtitle: "Switch language and background brightness instantly. Preferences are saved in this browser.",
    preferencesTitle: "Preferences",
    languageLabel: "Language",
    themeLabel: "Background brightness",
    systemTitle: "System"
  }
};

export const augmentationPresets = {
  clear_day: {
    brightness: 0.1,
    contrast: 0.1,
    shadow: false,
    rain: 0,
    fog: 0,
    motionBlur: 0,
    noise: 0,
    perspective: 0
  },
  low_light: {
    brightness: -0.25,
    contrast: 0.15,
    shadow: true,
    rain: 0,
    fog: 0,
    motionBlur: 0,
    noise: 0.05,
    perspective: 0
  },
  rainy: {
    brightness: -0.1,
    contrast: -0.05,
    shadow: false,
    rain: 0.4,
    fog: 0,
    motionBlur: 0.1,
    noise: 0,
    perspective: 0
  },
  foggy: {
    brightness: 0.05,
    contrast: -0.15,
    shadow: false,
    rain: 0,
    fog: 0.4,
    motionBlur: 0,
    noise: 0,
    perspective: 0
  },
  motion_camera: {
    brightness: 0,
    contrast: 0,
    shadow: false,
    rain: 0,
    fog: 0,
    motionBlur: 0.35,
    noise: 0.08,
    perspective: 0.06
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

export function applyLanguage(language) {
  const nextLanguage = language === "en" ? "en" : "zh-TW";
  appState.settings.language = nextLanguage;
  localStorage.setItem("vts-language", nextLanguage);

  const languageSelect = document.querySelector("#settings-language");
  if (languageSelect) languageSelect.value = nextLanguage;

  const dict = i18n[nextLanguage];
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (!dict[key]) return;
    el.textContent = dict[key];
  });

  const themeLabel = document.querySelector("[data-i18n='themeToggle']");
  if (themeLabel) {
    themeLabel.textContent = appState.settings.theme === "dark" ? dict.themeToggle : dict.themeToggleDark;
  }

  document.documentElement.lang = nextLanguage;
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
  const blockers = [];
  if (!project) blockers.push("尚未載入專案");
  if (project && rawImages.length === 0) blockers.push("尚未匯入資料集");
  if (project && !labelme.synced) blockers.push("尚未同步 LabelMe 標註");
  if (project && !splitComplete) blockers.push("尚未建立 Train / Val / Test");
  const trainReady = Boolean(project && rawImages.length > 0 && labelme.synced && splitComplete);

  return {
    hasProject: Boolean(project),
    projectName: project?.project_name || "尚未載入專案",
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
    labelme
  };
}
