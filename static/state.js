import { eventBus } from "./event_bus.js";

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
  inferenceLastResult: null,
  inferenceRunning: false,
  inferenceSelectedModelId: "",
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
    navAutoLabeling: "自動標註",
    navExport: "匯出",
    navHistory: "歷史紀錄",
    navSettings: "設定",
    settingsTitle: "設定",
    settingsSubtitle: "即時切換語言與背景亮度，偏好會儲存在目前瀏覽器。",
    preferencesTitle: "偏好設定",
    languageLabel: "語言",
    themeLabel: "背景亮度",
    systemTitle: "系統",

    "training.title": "模型訓練控制台",
    "training.subtitle": "先檢查訓練條件，修正阻擋項目後再設定並啟動訓練。",
    "training.card.dataset": "資料集",
    "training.card.annotation": "標註",
    "training.card.split": "資料分散",
    "training.card.startStatus": "啟動狀態",
    "training.card.images": "圖片：{count}",
    "training.card.annotated": "已標註：{annotated} / 缺少：{missing}",
    "training.card.trainValTest": "Train / Val / Test：{train} / {val} / {test}",
    "training.card.readinessPass": "就緒檢查：通過",
    "training.card.readinessBlocked": "就緒檢查：{count} 個阻擋項目",
    "training.status.ready": "可訓練",
    "training.status.blocked": "已阻擋",
    "training.status.missing": "缺少",
    "training.status.splitReady": "已建立",
    "training.config.title": "訓練設定",
    "training.config.locked": "資料集、LabelMe 標註與 Train / Val / Test 尚未就緒前，設定會先鎖定。",
    "training.config.lockedRunning": "訓練執行中，設定已鎖定。",
    "training.config.lockedStopping": "正在停止訓練，設定暫時鎖定。",
    "training.tab.simple": "簡易",
    "training.tab.advanced": "進階",
    "training.runName": "Run 名稱",
    "training.runNamePlaceholder": "留空會自動產生 run_YYYYMMDD_HHMMSS",
    "training.model": "模型",
    "training.modelTooltip": "請選擇與專案任務相容的模型。Segmentation 專案需要 segmentation 模型。",
    "training.profile": "訓練設定檔",
    "training.profileBalanced": "平衡",
    "training.profileQuick": "快速測試",
    "training.profileAccuracy": "高準確率",
    "training.profileCustom": "自訂",
    "training.epochs": "Epochs",
    "training.epochsTooltip": "完整看過資料集的次數。數值越高訓練越久，也可能增加過擬合風險。",
    "training.batch": "Batch Size",
    "training.batchTooltip": "每次送入模型的圖片數量。數值越高越吃 VRAM。",
    "training.imgsz": "Image Size",
    "training.imgszTooltip": "訓練輸入尺寸。尺寸越大細節越多，但速度更慢且更吃記憶體。",
    "training.device": "裝置",
    "training.deviceTooltip": "有 CUDA 時建議使用 GPU；CPU 可執行但訓練速度較慢。",
    "training.autoRecommend": "自動建議",
    "training.autoRecommendDefault": "會依資料量與硬體狀態產生建議。",
    "training.autoRecommendButton": "產生建議",
    "training.lr": "Learning Rate",
    "training.lrTooltip": "控制每次更新權重的幅度。過高可能不穩，過低會訓練很慢。",
    "training.optimizer": "Optimizer",
    "training.optimizerTooltip": "權重更新方法。多數情況建議使用 auto。",
    "training.patience": "Patience",
    "training.patienceTooltip": "Early stopping 等待改善的 epoch 數，避免無效訓練。",
    "training.workers": "Workers",
    "training.workersTooltip": "資料載入工作數。太高可能造成 CPU 或磁碟壓力。",
    "training.seed": "Seed",
    "training.seedTooltip": "固定隨機種子，讓訓練結果較容易重現。",
    "training.savePeriod": "Save Period",
    "training.savePeriodTooltip": "每 N 個 epochs 儲存一次 checkpoint。",
    "training.closeMosaic": "Close Mosaic Epochs",
    "training.closeMosaicTooltip": "最後幾個 epochs 關閉 mosaic augmentation，提高收斂穩定性。",
    "training.ampTooltip": "混合精度可降低 VRAM 使用量，需 GPU 支援。",
    "training.cacheTooltip": "快取資料可加速訓練，但會占用更多記憶體或磁碟。",
    "training.startDisabled": "Start Training 已停用",
    "training.start": "開始訓練",
    "training.stop": "停止訓練",
    "training.monitor.title": "即時訓練監控",
    "training.monitor.emptyTitle": "目前沒有進行中的訓練",
    "training.monitor.emptySubtitle": "就緒檢查通過後，開始訓練即可看到即時進度。",
    "training.monitor.status": "狀態",
    "training.monitor.progress": "進度",
    "training.monitor.loss": "Loss",
    "training.metrics.title": "訓練指標",
    "training.metrics.emptyTitle": "尚無訓練指標",
    "training.metrics.emptySubtitle": "完成一次訓練後，這裡會顯示圖表與結果摘要。",
    "training.metrics.primary": "主要指標",
    "training.metrics.lossBreakdown": "Loss 分解",
    "training.metrics.mask": "Mask 指標",
    "training.metrics.box": "Box 指標",
    "training.metrics.hardware": "硬體指標",
    "training.metrics.report": "報告檢視",
    "training.metrics.showRaw": "顯示原始資料",
    "training.metrics.showSmooth": "顯示 EMA 平滑",
    "training.metrics.smoothFactor": "平滑係數",
    "training.convergence": "收斂狀態",
    "training.bestEpoch": "最佳 Epoch",
    "training.platformScore": "平台評分",
    "training.suggestions.empty": "完成訓練後會產生建議。",
    "training.logs.title": "訓練紀錄",
    "training.logs.epochHistory": "Epoch 歷史",
    "training.logs.eventLog": "事件紀錄",
    "training.logs.noEpoch": "尚無 epoch 紀錄",
    "training.logs.noEvent": "尚無事件紀錄",
    "training.artifacts.title": "訓練產物",
    "training.artifacts.empty": "完成訓練後會列出 best.pt、last.pt、metrics 等檔案。",
    "training.runHistory.title": "訓練歷史",
    "training.runHistory.empty": "尚無訓練歷史。",
    "training.readiness.blocked": "訓練尚未就緒",
    "training.readiness.ready": "訓練已就緒",
    "training.readiness.fixBeforeStart": "請先修正以下阻擋項目，再開始訓練。",
    "training.readiness.readyDetail": "資料集、LabelMe 標註與資料分散已就緒，可以開始訓練。",
    "training.blocker.noProject": "尚未開啟專案",
    "training.blocker.noDataset": "尚未匯入資料集",
    "training.blocker.labelme": "LabelMe 標註尚未同步",
    "training.blocker.split": "尚未建立 Train / Val / Test 分散",
    "training.blocker.model": "目前模型不是 segmentation 模型",
    "training.action.openProject": "開啟或建立專案",
    "training.action.importDataset": "前往 Dataset 匯入資料",
    "training.action.syncLabelMe": "前往 LabelMe 同步標註",
    "training.action.createSplit": "建立資料分散",
    "training.action.chooseSegModel": "選擇 segmentation 模型",
    "training.toast.segModel": "目前專案是 segmentation，請選擇 segmentation 模型。",
    "training.toast.blocked": "訓練尚未就緒，請先修正阻擋項目。",
    "training.toast.started": "訓練已啟動",
    "training.toast.startFailed": "啟動訓練失敗：{message}",
    "training.toast.stopSent": "已送出停止訓練請求",
    "training.toast.stopFailed": "停止訓練失敗：{message}",
    "training.recommend.noProject": "請先開啟專案，才能產生訓練建議。",
    "training.recommend.noGpu": "未偵測到 GPU，CPU 可執行但訓練會很慢。",
    "training.recommend.low": "VRAM 較低，建議使用較小模型、batch 4、image size 640。",
    "training.recommend.medium": "VRAM 適中，segmentation 建議 batch 8、image size 640。",
    "training.recommend.high": "VRAM 充足，可嘗試 batch 16 或 image size 768。"
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
    navAutoLabeling: "Auto-Labeling",
    navExport: "Export",
    navHistory: "History",
    navSettings: "Settings",
    settingsTitle: "Settings",
    settingsSubtitle: "Switch language and background brightness instantly. Preferences are saved in this browser.",
    preferencesTitle: "Preferences",
    languageLabel: "Language",
    themeLabel: "Background brightness",
    systemTitle: "System",

    "training.title": "Training Control Console",
    "training.subtitle": "Check training readiness first, fix blockers, then configure and start a controlled training run.",
    "training.card.dataset": "Dataset",
    "training.card.annotation": "Annotation",
    "training.card.split": "Split",
    "training.card.startStatus": "Start Status",
    "training.card.images": "Images: {count}",
    "training.card.annotated": "Annotated: {annotated} / Missing: {missing}",
    "training.card.trainValTest": "Train / Val / Test: {train} / {val} / {test}",
    "training.card.readinessPass": "Readiness: pass",
    "training.card.readinessBlocked": "Readiness: {count} blocker{plural}",
    "training.status.ready": "Ready",
    "training.status.blocked": "Blocked",
    "training.status.missing": "Missing",
    "training.status.splitReady": "Ready",
    "training.config.title": "Training Configuration",
    "training.config.locked": "Training configuration is locked until Dataset, LabelMe annotations, and Split are ready.",
    "training.config.lockedRunning": "Training configuration is locked while a run is active.",
    "training.config.lockedStopping": "Training is stopping. Configuration remains locked.",
    "training.tab.simple": "Simple",
    "training.tab.advanced": "Advanced",
    "training.runName": "Run Name",
    "training.runNamePlaceholder": "Optional, for example run_YYYYMMDD_HHMMSS",
    "training.model": "Model",
    "training.modelTooltip": "Select a model compatible with the current project task. Segmentation projects should use a segmentation model.",
    "training.profile": "Training Profile",
    "training.profileBalanced": "Balanced",
    "training.profileQuick": "Quick Test",
    "training.profileAccuracy": "High Accuracy",
    "training.profileCustom": "Custom",
    "training.epochs": "Epochs",
    "training.epochsTooltip": "One epoch means the model has seen the full training dataset once. More epochs can improve learning but can also overfit.",
    "training.batch": "Batch Size",
    "training.batchTooltip": "Number of images processed at once. Larger batches use more VRAM.",
    "training.imgsz": "Image Size",
    "training.imgszTooltip": "Input image size for training. Higher sizes may improve detail but use more memory.",
    "training.device": "Hardware Device",
    "training.deviceTooltip": "Use GPU when CUDA is available. CPU training is possible but much slower.",
    "training.autoRecommend": "Auto recommendation",
    "training.autoRecommendDefault": "Settings will be checked after project and hardware status are loaded.",
    "training.autoRecommendButton": "Auto Recommend Settings",
    "training.lr": "Learning Rate",
    "training.lrTooltip": "Initial optimizer learning rate. Keep default unless you know why it should change.",
    "training.optimizer": "Optimizer",
    "training.optimizerTooltip": "Optimizer used during training. Auto is recommended for most projects.",
    "training.patience": "Patience",
    "training.patienceTooltip": "Early stopping patience. Training stops if validation quality does not improve for this many epochs.",
    "training.workers": "Workers",
    "training.workersTooltip": "Number of data loading worker processes. Higher values may speed loading but use more CPU and memory.",
    "training.seed": "Seed",
    "training.seedTooltip": "Random seed used to make training more reproducible.",
    "training.savePeriod": "Save Period",
    "training.savePeriodTooltip": "Save a checkpoint every N epochs.",
    "training.closeMosaic": "Close Mosaic Epochs",
    "training.closeMosaicTooltip": "Disable mosaic augmentation near the end of training to improve convergence.",
    "training.ampTooltip": "Mixed precision can reduce VRAM usage and speed up GPU training.",
    "training.cacheTooltip": "Cache images in memory or disk to speed data loading. Requires enough system resources.",
    "training.startDisabled": "Start Training is disabled.",
    "training.start": "Start Training",
    "training.stop": "Stop Training",
    "training.monitor.title": "Live Training Monitor",
    "training.monitor.emptyTitle": "No active training run.",
    "training.monitor.emptySubtitle": "Start training after readiness checks pass.",
    "training.monitor.status": "Status",
    "training.monitor.progress": "Progress",
    "training.monitor.loss": "Loss",
    "training.metrics.title": "Metrics Dashboard",
    "training.metrics.emptyTitle": "No training metrics yet.",
    "training.metrics.emptySubtitle": "Complete a training run to view charts, artifacts, and trend diagnostics.",
    "training.metrics.primary": "Primary Metrics",
    "training.metrics.lossBreakdown": "Loss Breakdown",
    "training.metrics.mask": "Mask Metrics",
    "training.metrics.box": "Box Metrics",
    "training.metrics.hardware": "Hardware Metrics",
    "training.metrics.report": "Report View",
    "training.metrics.showRaw": "Show Raw Curve",
    "training.metrics.showSmooth": "Show EMA Smooth",
    "training.metrics.smoothFactor": "Smooth Factor (?):",
    "training.convergence": "Convergence Diagnostic",
    "training.bestEpoch": "Best Epoch:",
    "training.platformScore": "Platform Score:",
    "training.suggestions.empty": "Complete a run to generate training suggestions.",
    "training.logs.title": "History & Event Logs",
    "training.logs.epochHistory": "Epoch History",
    "training.logs.eventLog": "Event Log",
    "training.logs.noEpoch": "No epoch history yet.",
    "training.logs.noEvent": "No training events yet.",
    "training.artifacts.title": "Model Artifacts",
    "training.artifacts.empty": "No artifacts yet. Complete a training run to see best.pt, last.pt, metrics, and reports.",
    "training.runHistory.title": "Run History",
    "training.runHistory.empty": "No training runs yet.",
    "training.readiness.blocked": "Training Readiness: Blocked",
    "training.readiness.ready": "Training Readiness: Ready",
    "training.readiness.fixBeforeStart": "Fix these items before editing training settings or starting a run.",
    "training.readiness.readyDetail": "Dataset, LabelMe annotations, split, model compatibility, and basic hardware checks are ready for training.",
    "training.blocker.noProject": "No project is currently opened.",
    "training.blocker.noDataset": "No dataset images found.",
    "training.blocker.labelme": "LabelMe annotations have not been synced.",
    "training.blocker.split": "Train / Val / Test split is missing.",
    "training.blocker.model": "Selected model is not compatible with segmentation training.",
    "training.action.openProject": "Create or open a project.",
    "training.action.importDataset": "Import images in Dataset.",
    "training.action.syncLabelMe": "Sync annotations in LabelMe.",
    "training.action.createSplit": "Create a split before training.",
    "training.action.chooseSegModel": "Choose a segmentation model.",
    "training.toast.segModel": "This project is segmentation. Please select a segmentation model.",
    "training.toast.blocked": "Training is blocked. Fix readiness blockers first.",
    "training.toast.started": "Training started.",
    "training.toast.startFailed": "Failed to start training: {message}",
    "training.toast.stopSent": "Stop request sent. Waiting for training process to exit.",
    "training.toast.stopFailed": "Failed to stop training: {message}",
    "training.recommend.noProject": "Open a project before generating training recommendations.",
    "training.recommend.noGpu": "GPU is not available. CPU mode is safer, but training will be slow.",
    "training.recommend.low": "VRAM risk: Low. Current settings look reasonable.",
    "training.recommend.medium": "VRAM risk: Medium. Recommended: batch 8, image size 640 for segmentation stability.",
    "training.recommend.high": "VRAM risk: High. Recommended: batch 4, image size 640."
  }
};

export function t(key, params = {}) {
  const lang = appState.settings.language === "en" ? "en" : "zh-TW";
  const fallback = i18n.en?.[key] ?? key;
  const template = i18n[lang]?.[key] ?? fallback;
  return String(template).replace(/\{(\w+)\}/g, (_, name) => params[name] ?? "");
}

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
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    if (!dict[key]) return;
    el.setAttribute("placeholder", dict[key]);
  });
  document.querySelectorAll("[data-i18n-tooltip]").forEach((el) => {
    const key = el.dataset.i18nTooltip;
    if (!dict[key]) return;
    el.dataset.tooltip = dict[key];
  });

  const themeLabel = document.querySelector("[data-i18n='themeToggle']");
  if (themeLabel) {
    themeLabel.textContent = appState.settings.theme === "dark" ? dict.themeToggle : dict.themeToggleDark;
  }

  document.documentElement.lang = nextLanguage;
  eventBus.emit("language-changed", nextLanguage);
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
