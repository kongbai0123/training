// Vision Training Studio - Phase 1 UI Redesign

const appState = {
  currentPage: "dashboard",
  currentProjectId: null,
  currentProject: null,
  projects: [],
  datasetVisibleLimit: 80,
  newProjectClasses: [],
  pendingDeleteProjectId: null,
  trainingStatus: null,
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

document.addEventListener("DOMContentLoaded", async () => {
  initPreferences();
  bindNavigation();
  bindFloatingTooltips();
  bindPreferences();
  bindProjectActions();
  bindDeleteProjectModal();
  bindDatasetActions();
  bindSplitActions();
  bindAugmentationActions();
  bindTrainingActions();
  bindExportActions();
  bindLabelMeActions();
  await loadProjects({ autoOpenLatest: true });
  navigate("dashboard");
});

const augmentationPresets = {
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

const fixedAugmentationValues = {
  brightness: 0.2,
  contrast: 0.2,
  rain: 0.4,
  fog: 0.4,
  motionBlur: 0.3,
  noise: 0.08,
  perspective: 0.06
};

let isBalancingSplitRatios = false;

function colorForLabel(label) {
  const palette = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#be123c", "#4f46e5"];
  const text = String(label || "label");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  }
  return palette[hash % palette.length];
}

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return [...document.querySelectorAll(selector)];
}

function bindFloatingTooltips() {
  const tooltip = document.createElement("div");
  tooltip.className = "floating-tooltip";
  tooltip.setAttribute("role", "tooltip");
  document.body.appendChild(tooltip);

  const showTooltip = (target) => {
    const text = target?.dataset?.tooltip;
    if (!text) return;
    const parts = splitTooltipText(text);
    tooltip.innerHTML = `<ul>${parts.map((part) => `<li>${escapeHtml(part)}</li>`).join("")}</ul>`;
    tooltip.classList.add("is-visible");
    positionFloatingTooltip(tooltip, target);
  };

  const hideTooltip = () => {
    tooltip.classList.remove("is-visible");
  };

  document.addEventListener("mouseover", (event) => {
    const target = event.target.closest?.(".info-icon");
    if (target) showTooltip(target);
  });
  document.addEventListener("focusin", (event) => {
    const target = event.target.closest?.(".info-icon");
    if (target) showTooltip(target);
  });
  document.addEventListener("mouseout", (event) => {
    if (event.target.closest?.(".info-icon")) hideTooltip();
  });
  document.addEventListener("focusout", (event) => {
    if (event.target.closest?.(".info-icon")) hideTooltip();
  });
  window.addEventListener("scroll", hideTooltip, true);
  window.addEventListener("resize", hideTooltip);
}

function splitTooltipText(text) {
  const cleaned = String(text || "").trim();
  if (!cleaned) return [];
  return cleaned
    .split(/(?:\n|；|;|。)/)
    .map((part) => part.trim().replace(/[，,]\s*$/, ""))
    .filter(Boolean);
}

function positionFloatingTooltip(tooltip, target) {
  const margin = 12;
  const targetRect = target.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  let left = targetRect.left + targetRect.width / 2 - tooltipRect.width / 2;
  let top = targetRect.top - tooltipRect.height - 10;

  left = Math.max(margin, Math.min(left, window.innerWidth - tooltipRect.width - margin));
  if (top < margin) top = targetRect.bottom + 10;
  top = Math.max(margin, Math.min(top, window.innerHeight - tooltipRect.height - margin));

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
}

function setText(selector, value) {
  const el = qs(selector);
  if (el) el.textContent = value;
}

function setHTML(selector, html) {
  const el = qs(selector);
  if (el) el.innerHTML = html;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  const toast = qs("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3200);
}

const i18n = {
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

function initPreferences() {
  applyTheme(appState.settings.theme);
  applyLanguage(appState.settings.language);
}

function bindPreferences() {
  qs("#btn-theme-toggle")?.addEventListener("click", () => {
    const nextTheme = appState.settings.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
  });

  qs("#settings-language")?.addEventListener("change", (event) => {
    applyLanguage(event.target.value);
  });

  qs("#settings-theme")?.addEventListener("change", (event) => {
    applyTheme(event.target.value);
  });
}

function applyTheme(theme) {
  const nextTheme = theme === "light" ? "light" : "dark";
  appState.settings.theme = nextTheme;
  localStorage.setItem("vts-theme", nextTheme);
  document.body.dataset.theme = nextTheme;

  const themeSelect = qs("#settings-theme");
  if (themeSelect) themeSelect.value = nextTheme;

  const icon = qs("#btn-theme-toggle i");
  if (icon) {
    icon.className = nextTheme === "dark" ? "fa-solid fa-sun" : "fa-solid fa-moon";
  }
  applyLanguage(appState.settings.language);
}

function applyLanguage(language) {
  const nextLanguage = language === "en" ? "en" : "zh-TW";
  appState.settings.language = nextLanguage;
  localStorage.setItem("vts-language", nextLanguage);

  const languageSelect = qs("#settings-language");
  if (languageSelect) languageSelect.value = nextLanguage;

  const dict = i18n[nextLanguage];
  qsa("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    if (!dict[key]) return;
    el.textContent = dict[key];
  });

  const themeLabel = qs("[data-i18n='themeToggle']");
  if (themeLabel) {
    themeLabel.textContent = appState.settings.theme === "dark" ? dict.themeToggle : dict.themeToggleDark;
  }

  document.documentElement.lang = nextLanguage;
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = "";
    try {
      const data = await res.json();
      detail = data.detail || JSON.stringify(data);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  const contentType = res.headers.get("content-type") || "";
  return contentType.includes("application/json") ? res.json() : res.text();
}

async function collectDroppedFiles(dataTransfer) {
  const items = [...(dataTransfer?.items || [])];
  if (!items.length) return [...(dataTransfer?.files || [])];

  const entries = items
    .map((item) => item.webkitGetAsEntry?.())
    .filter(Boolean);

  if (!entries.length) return [...(dataTransfer?.files || [])];

  const nestedFiles = await Promise.all(entries.map(readEntryFiles));
  return nestedFiles.flat();
}

function readEntryFiles(entry) {
  if (!entry) return Promise.resolve([]);
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file((file) => resolve([file]), () => resolve([]));
    });
  }
  if (!entry.isDirectory) return Promise.resolve([]);

  const reader = entry.createReader();
  const allEntries = [];

  return new Promise((resolve) => {
    const readBatch = () => {
      reader.readEntries(async (entries) => {
        if (!entries.length) {
          const nested = await Promise.all(allEntries.map(readEntryFiles));
          resolve(nested.flat());
          return;
        }
        allEntries.push(...entries);
        readBatch();
      }, () => resolve([]));
    };
    readBatch();
  });
}

function bindNavigation() {
  qsa("[data-page]").forEach((btn) => {
    btn.addEventListener("click", () => navigate(btn.dataset.page));
  });
  document.addEventListener("click", (event) => {
    const navTarget = event.target.closest("[data-nav]");
    if (!navTarget) return;
    event.preventDefault();
    navigate(navTarget.dataset.nav);
  });
  qs("#btn-dashboard-refresh")?.addEventListener("click", () => refreshAll());
  qs("#btn-header-history")?.addEventListener("click", openHistoryModal);
  qs("#btn-close-history")?.addEventListener("click", closeHistoryModal);
  qs("#project-history-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "project-history-modal") closeHistoryModal();
  });
}

function navigate(pageId) {
  appState.currentPage = pageId || "dashboard";
  qsa(".sidebar-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === appState.currentPage);
  });
  qsa(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${appState.currentPage}`);
  });
  renderAll();
}

// Compatibility shim for old call sites. It no longer blocks page entry.
function switchTab(tabId) {
  const map = {
    "tab-project": "projects",
    "tab-dataset": "dataset",
    "tab-label": "labelme",
    "tab-split": "split",
    "tab-train": "training",
    "tab-eval": "evaluation",
    "tab-export": "export"
  };
  navigate(map[tabId] || tabId || "dashboard");
}

async function refreshAll() {
  await loadProjects({ autoOpenLatest: false });
  if (appState.currentProjectId) {
    await openProject(appState.currentProjectId, { stayOnPage: true });
  }
  showToast("狀態已重新整理");
}

async function loadProjects(options = {}) {
  try {
    appState.projects = await apiFetch("/api/projects");
    qs("#api-status-dot")?.classList.add("online");
    qs("#api-status-dot")?.classList.remove("offline");
    renderRecentProjects(appState.projects);
    renderProjectHistory(appState.projects);
    if (options.autoOpenLatest && !appState.currentProjectId && appState.projects.length > 0) {
      await openProject(appState.projects[0].project_id, { stayOnPage: true });
      return;
    }
    renderAll();
  } catch (err) {
    qs("#api-status-dot")?.classList.add("offline");
    showToast(`無法讀取專案清單：${err.message}`);
    renderAll();
  }
}

async function openProject(projectId, options = {}) {
  if (!projectId) return;
  try {
    appState.currentProject = await apiFetch(`/api/projects/${projectId}`);
    appState.currentProjectId = projectId;
    appState.currentProjectClasses = [...(appState.currentProject?.class_names || [])];
    setText("#current-project-title", appState.currentProject.project_name || projectId);
    updateLabelMeState();
    await checkCurrentTrainStatus();
    renderAll();
    if (!options.stayOnPage) navigate(options.page || "dashboard");
  } catch (err) {
    showToast(`無法載入專案：${err.message}`);
  }
}

function bindProjectActions() {
  qs("#btn-reload-projects")?.addEventListener("click", () => loadProjects({ autoOpenLatest: false }));
  qs("#btn-add-project-class")?.addEventListener("click", addProjectClassFromInput);
  qs("#new-project-class-input")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addProjectClassFromInput();
  });
  qs("#new-project-class-list")?.addEventListener("click", (event) => {
    const removeBtn = event.target.closest("[data-remove-class]");
    if (!removeBtn) return;
    const className = removeBtn.dataset.removeClass;
    appState.newProjectClasses = appState.newProjectClasses.filter((item) => item !== className);
    renderNewProjectClassList();
  });
  renderNewProjectClassList();

  qs("#form-create-project")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = qs("#new-project-name").value.trim();
    const type = qs("#new-project-type").value;
    const classes = [...appState.newProjectClasses];

    if (!name || classes.length === 0) {
      showToast("請輸入專案名稱與至少一個類別");
      return;
    }

    try {
      const project = await apiFetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: name, task_type: type, class_names: classes })
      });
      qs("#form-create-project").reset();
      appState.newProjectClasses = [];
      renderNewProjectClassList();
      await loadProjects({ autoOpenLatest: false });
      await openProject(project.project_id, { page: "dashboard" });
      showToast("專案已建立");
    } catch (err) {
      showToast(`建立專案失敗：${err.message}`);
    }
  });
}

function addProjectClassFromInput() {
  const input = qs("#new-project-class-input");
  const rawValue = input?.value?.trim();
  if (!rawValue) return;

  const values = rawValue
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

  let changed = false;
  values.forEach((value) => {
    const exists = appState.newProjectClasses.some((item) => item.toLowerCase() === value.toLowerCase());
    if (exists) return;
    appState.newProjectClasses.push(value);
    changed = true;
  });

  if (input) input.value = "";
  if (!changed) {
    showToast("類別已存在");
  }
  renderNewProjectClassList();
}

function renderNewProjectClassList() {
  const box = qs("#new-project-class-list");
  if (!box) return;

  if (appState.newProjectClasses.length === 0) {
    box.innerHTML = `<div class="empty-class-list">尚未新增類別</div>`;
    return;
  }

  box.innerHTML = appState.newProjectClasses.map((className) => `
    <span class="class-chip">
      ${escapeHtml(className)}
      <button type="button" data-remove-class="${escapeHtml(className)}" aria-label="Remove ${escapeHtml(className)}">
        <i class="fa-solid fa-xmark"></i>
      </button>
    </span>
  `).join("");
}

function renderProjectHistory(projects) {
  const html = renderProjectList(projects, { includeDelete: true });
  setHTML("#project-history-list", html);
  setHTML("#history-list", html);
  bindProjectListButtons();
}

function renderProjectList(projects, options = {}) {
  if (!projects || projects.length === 0) {
    return `<div class="empty-state">目前沒有專案。請先建立新專案。</div>`;
  }
  return projects.map((project) => {
    const progress = project.annotation_progress || {};
    return `
      <article class="list-item">
        <div>
          <h3>${escapeHtml(project.project_name || project.project_id)}</h3>
          <p>${escapeHtml(project.task_type || "--")} · ${progress.annotated || 0}/${progress.total || 0} annotated · ${escapeHtml(project.updated_at || "")}</p>
        </div>
        <div class="button-row">
          <button class="btn btn-secondary btn-sm" data-open-project="${escapeHtml(project.project_id)}">Open</button>
          ${options.includeDelete ? `<button class="icon-btn" data-delete-project="${escapeHtml(project.project_id)}" title="Delete"><i class="fa-solid fa-trash"></i></button>` : ""}
        </div>
      </article>
    `;
  }).join("");
}

function bindProjectListButtons() {
  qsa("[data-open-project]").forEach((btn) => {
    btn.addEventListener("click", () => {
      closeHistoryModal();
      openProject(btn.dataset.openProject, { page: "dashboard" });
    });
  });
  qsa("[data-delete-project]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const projectId = btn.dataset.deleteProject;
      openDeleteProjectModal(projectId);
    });
  });
}

function bindDeleteProjectModal() {
  qs("#btn-close-delete-project")?.addEventListener("click", closeDeleteProjectModal);
  qs("#btn-cancel-delete-project")?.addEventListener("click", closeDeleteProjectModal);
  qs("#delete-project-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "delete-project-modal") closeDeleteProjectModal();
  });
  qs("#btn-confirm-delete-project")?.addEventListener("click", confirmDeleteProject);
}

function openDeleteProjectModal(projectId) {
  const project = appState.projects.find((item) => item.project_id === projectId);
  appState.pendingDeleteProjectId = projectId;
  setText("#delete-project-message", `確定要刪除專案「${project?.project_name || projectId}」？此操作無法復原。`);
  const btn = qs("#btn-confirm-delete-project");
  if (btn) {
    btn.disabled = false;
    btn.classList.remove("btn-disabled");
    btn.innerHTML = `<i class="fa-solid fa-trash"></i> 刪除`;
  }
  const modal = qs("#delete-project-modal");
  if (modal) modal.hidden = false;
}

function closeDeleteProjectModal() {
  appState.pendingDeleteProjectId = null;
  setText("#delete-project-message", "確定要刪除此專案？此操作無法復原。");
  const modal = qs("#delete-project-modal");
  if (modal) modal.hidden = true;
}

async function confirmDeleteProject() {
  const projectId = appState.pendingDeleteProjectId;
  if (!projectId) return closeDeleteProjectModal();

  const btn = qs("#btn-confirm-delete-project");
  if (btn) {
    btn.disabled = true;
    btn.classList.add("btn-disabled");
    btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 刪除中`;
  }

  try {
    await apiFetch(`/api/projects/${projectId}`, { method: "DELETE" });
    if (appState.currentProjectId === projectId) {
      appState.currentProjectId = null;
      appState.currentProject = null;
      appState.trainingStatus = null;
      updateLabelMeState();
      setText("#current-project-title", "尚未載入專案");
    }
    closeDeleteProjectModal();
    await loadProjects({ autoOpenLatest: false });
    renderAll();
    showToast("專案已刪除");
  } catch (err) {
    if (err.message && err.message.includes("Project not found")) {
      closeDeleteProjectModal();
      await loadProjects({ autoOpenLatest: false });
      renderAll();
      showToast("專案已不存在，已重新整理清單");
      return;
    }
    showToast(`刪除失敗：${err.message}`);
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-disabled");
      btn.innerHTML = `<i class="fa-solid fa-trash"></i> 刪除`;
    }
  }
}

function openHistoryModal() {
  const modal = qs("#project-history-modal");
  setHTML("#modal-project-list", renderProjectList(appState.projects, { includeDelete: false }));
  bindProjectListButtons();
  if (modal) modal.hidden = false;
}

function closeHistoryModal() {
  const modal = qs("#project-history-modal");
  if (modal) modal.hidden = true;
}

function bindDatasetActions() {
  // 類別管理事件綁定
  qs("#btn-dataset-add-class")?.addEventListener("click", () => {
    const input = qs("#input-dataset-new-class");
    const name = input?.value.trim();
    if (!name) return;
    if (!appState.currentProjectClasses) {
      appState.currentProjectClasses = [];
    }
    if (appState.currentProjectClasses.includes(name)) {
      showToast("此類別已存在！");
      return;
    }
    appState.currentProjectClasses.push(name);
    if (input) input.value = "";
    renderDatasetClassesEditList();
  });

  qs("#input-dataset-new-class")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      qs("#btn-dataset-add-class")?.click();
    }
  });

  qs("#dataset-classes-list-box")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove-dataset-class]");
    if (!btn) return;
    const name = btn.dataset.removeDatasetClass;
    appState.currentProjectClasses = (appState.currentProjectClasses || []).filter(c => c !== name);
    renderDatasetClassesEditList();
  });

  qs("#btn-save-dataset-classes")?.addEventListener("click", async () => {
    if (!appState.currentProjectId) {
      showToast("請先選擇專案！");
      return;
    }
    const btn = qs("#btn-save-dataset-classes");
    if (btn) btn.disabled = true;
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/classes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ class_names: appState.currentProjectClasses || [] })
      });
      showToast("類別更新成功！");
      await openProject(appState.currentProjectId, { stayOnPage: true });
    } catch (err) {
      showToast(`類別更新失敗：${err.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  qs("#btn-import-local")?.addEventListener("click", async () => {
    const path = qs("#input-local-folder").value.trim();
    if (!path) return showToast("請輸入圖片資料夾路徑");
    const formData = new FormData();
    formData.append("path", path);
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-local`, {
        method: "POST",
        body: formData
      });
      showToast(data.message || "圖片匯入完成");
      await openProject(appState.currentProjectId, { stayOnPage: true });
    } catch (err) {
      showToast(`匯入圖片失敗：${err.message}`);
    }
  });

  qs("#btn-import-video")?.addEventListener("click", async () => {
    const videoPath = qs("#input-video-path").value.trim();
    const fps = qs("#input-video-fps").value || "1";
    if (!videoPath) return showToast("請輸入影片路徑");
    const formData = new FormData();
    formData.append("video_path", videoPath);
    formData.append("fps", fps);
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-video`, {
        method: "POST",
        body: formData
      });
      showToast(data.message || "影片抽幀完成");
      await openProject(appState.currentProjectId, { stayOnPage: true });
    } catch (err) {
      showToast(`影片抽幀失敗：${err.message}`);
    }
  });

  // 影片拖曳上傳區 (Dropzone)
  const videoDropZone = qs("#video-drop-zone");
  const inputVideoFile = qs("#input-video-file");
  
  if (videoDropZone && typeof Dropzone !== "undefined") {
    if (inputVideoFile) inputVideoFile.style.display = "none";
    if (!videoDropZone.dropzone) {
      new Dropzone(videoDropZone, {
        url: function() {
          return `/api/projects/${appState.currentProjectId}/upload-video`;
        },
        paramName: "file",
        acceptedFiles: "video/*",
        maxFilesize: 2048,
        autoProcessQueue: true,
        previewsContainer: document.createElement("div"),
        previewTemplate: '<div style="display:none"></div>',
        init: function() {
          this.on("addedfile", function(file) {
            if (!appState.currentProjectId) {
              showToast("請先載入或建立專案！");
              this.removeFile(file);
              return;
            }
            showToast("正在上傳影片並提取影格...");
          });

          this.on("sending", function(file, xhr, formData) {
            const fpsVal = qs("#input-video-fps")?.value || "1";
            formData.append("fps", fpsVal);
          });

          this.on("success", async function(file, response) {
            let data = response;
            if (typeof response === "string") {
              try {
                data = JSON.parse(response);
              } catch (e) {
                data = { message: response };
              }
            }
            showToast(data.message || "影片抽幀完成！");
            await openProject(appState.currentProjectId, { stayOnPage: true });
          });

          this.on("error", function(file, message) {
            let errMsg = message;
            if (typeof message === "object") {
              errMsg = message.detail || message.message || JSON.stringify(message);
            }
            showToast(`影片抽幀失敗：${errMsg}`);
          });

          this.on("queuecomplete", function() {
            this.removeAllFiles(true);
          });
        }
      });
    }
  } else {
    videoDropZone?.addEventListener("click", () => {
      inputVideoFile?.click();
    });
    
    inputVideoFile?.addEventListener("change", async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      if (!appState.currentProjectId) {
        showToast("請先載入或建立專案！");
        if (inputVideoFile) inputVideoFile.value = "";
        return;
      }
      
      const fpsVal = qs("#input-video-fps")?.value || "1";
      const formData = new FormData();
      formData.append("file", file);
      formData.append("fps", fpsVal);
      
      showToast("正在上傳影片並提取影格...");
      try {
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/upload-video`, {
          method: "POST",
          body: formData
        });
        showToast(data.message || "影片抽幀完成！");
        await openProject(appState.currentProjectId, { stayOnPage: true });
      } catch (err) {
        showToast(`影片抽幀失敗：${err.message}`);
      } finally {
        if (inputVideoFile) inputVideoFile.value = "";
      }
    });
  }

  qs("#btn-trigger-quality")?.addEventListener("click", async () => {
    try {
      const report = await apiFetch(`/api/projects/${appState.currentProjectId}/quality-check`, { method: "POST" });
      showToast(`品質檢查完成，Health Score: ${report.score}`);
      await openProject(appState.currentProjectId, { stayOnPage: true });
    } catch (err) {
      showToast(`品質檢查失敗：${err.message}`);
    }
  });

  qs("#btn-copy-zip-path")?.addEventListener("click", () => copyText(qs("#dataset-zip-storage-path")?.textContent));
  
  const zipDropZone = qs("#zip-drop-zone");
  const inputZipFile = qs("#input-zip-file");

  async function uploadDatasetFiles(files) {
    if (!appState.currentProjectId) {
      showToast("Please load a project first.");
      return;
    }

    const allFiles = [...files];
    if (allFiles.length === 0) {
      showToast("No files to upload.");
      return;
    }

    const zipFiles = allFiles.filter(file => file.name.toLowerCase().endsWith(".zip"));
    const mixedFiles = allFiles.filter(file => {
      const name = file.name.toLowerCase();
      return /\.(jpg|jpeg|png|bmp|json|txt)$/.test(name);
    });
    mixedFiles.sort((a, b) => {
      const rank = (file) => {
        const name = file.name.toLowerCase();
        if (/\.(jpg|jpeg|png|bmp)$/.test(name)) return 0;
        if (name.endsWith(".json")) return 1;
        if (name.endsWith(".txt")) return 2;
        return 3;
      };
      return rank(a) - rank(b);
    });

    if (zipFiles.length === 0 && mixedFiles.length === 0) {
      showToast("No supported files found. Use images, LabelMe JSON, YOLO TXT, or ZIP.");
      return;
    }

    let importedImages = 0;
    let importedJsons = 0;
    let importedTxts = 0;
    let skipped = Math.max(0, allFiles.length - zipFiles.length - mixedFiles.length);

    try {
      for (const zipFile of zipFiles) {
        const formData = new FormData();
        formData.append("file", zipFile, zipFile.name);
        showToast(`Importing ZIP: ${zipFile.name}`);
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-zip`, {
          method: "POST",
          body: formData
        });
        importedImages += data.imported_images || 0;
        importedJsons += data.imported_jsons || 0;
        importedTxts += data.imported_txts || 0;
      }

      const batchSize = 500;
      for (let i = 0; i < mixedFiles.length; i += batchSize) {
        const batch = mixedFiles.slice(i, i + batchSize);
        const formData = new FormData();
        batch.forEach(file => {
          formData.append("files", file, file.webkitRelativePath || file.name);
        });
        showToast(`Importing folder files ${Math.floor(i / batchSize) + 1}/${Math.ceil(mixedFiles.length / batchSize)}...`);
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/upload-dataset-files`, {
          method: "POST",
          body: formData
        });
        importedImages += data.imported_images || 0;
        importedJsons += data.imported_jsons || 0;
        importedTxts += data.imported_txts || 0;
        skipped += data.skipped || 0;
      }

      showToast(`Import complete: images ${importedImages}, JSON ${importedJsons}, TXT ${importedTxts}, skipped ${skipped}`);
      await openProject(appState.currentProjectId, { stayOnPage: true });
    } catch (err) {
      showToast(`Dataset import failed: ${err.message}`);
    }
  }

  if (zipDropZone && inputZipFile) {
    if (zipDropZone.dropzone) zipDropZone.dropzone.destroy();
    inputZipFile.style.display = "none";
    inputZipFile.multiple = true;
    inputZipFile.setAttribute("webkitdirectory", "");
    inputZipFile.setAttribute("directory", "");

    zipDropZone.addEventListener("click", () => inputZipFile.click());

    inputZipFile.addEventListener("change", async (event) => {
      await uploadDatasetFiles([...(event.target.files || [])]);
      inputZipFile.value = "";
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      zipDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        zipDropZone.classList.add("dz-drag-hover");
      }, true);
    });

    ["dragleave", "drop"].forEach((eventName) => {
      zipDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        zipDropZone.classList.remove("dz-drag-hover");
      }, true);
    });

    zipDropZone.addEventListener("drop", async (event) => {
      const files = await collectDroppedFiles(event.dataTransfer);
      await uploadDatasetFiles(files);
    }, true);
  }

  qs("#search-image")?.addEventListener("input", () => {
    appState.datasetVisibleLimit = 80;
    renderDatasetPage(getProjectStatus(appState.currentProject));
  });
  qs("#filter-status")?.addEventListener("change", () => {
    appState.datasetVisibleLimit = 80;
    renderDatasetPage(getProjectStatus(appState.currentProject));
  });
  qs("#dataset-thumbnails")?.addEventListener("click", (event) => {
    if (!event.target.closest("#btn-load-more-images")) return;
    appState.datasetVisibleLimit += 80;
    renderDatasetPage(getProjectStatus(appState.currentProject));
  });
}

function bindSplitActions() {
  ["train", "val", "test"].forEach((key) => {
    qs(`#input-ratio-${key}`)?.addEventListener("input", () => rebalanceSplitRatios(key));
    qs(`#input-ratio-${key}`)?.addEventListener("change", () => rebalanceSplitRatios(key));
  });
  updateSplitRatioTotal();

  qs("#form-split-dataset")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    updateSplitRatioTotal();
    const train = Number(qs("#input-ratio-train").value) / 100;
    const val = Number(qs("#input-ratio-val").value) / 100;
    const test = Number(qs("#input-ratio-test").value) / 100;
    if (Math.abs(train + val + test - 1) > 0.01) {
      showToast("Train / Val / Test 比例總和必須為 100%");
      return;
    }
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/split`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          method: qs("#split-method").value,
          ratio: { train, val, test }
        })
      });
      renderSplitReportUI(data.report);
      showToast("資料分散完成");
      await openProject(appState.currentProjectId, { stayOnPage: true });
    } catch (err) {
      showToast(`資料分散失敗：${err.message}`);
    }
  });
}

function rebalanceSplitRatios(changedKey) {
  if (isBalancingSplitRatios) return;
  const keys = ["train", "val", "test"];
  const mins = { train: 10, val: 5, test: 5 };
  const fields = Object.fromEntries(keys.map((key) => [key, qs(`#input-ratio-${key}`)]));
  if (!fields[changedKey]) return;

  isBalancingSplitRatios = true;
  const others = keys.filter((key) => key !== changedKey);
  const changedMax = 100 - mins[others[0]] - mins[others[1]];
  const changedValue = clampNumber(Number(fields[changedKey].value), mins[changedKey], changedMax);
  const remaining = 100 - changedValue;
  const firstCurrent = Math.max(0, Number(fields[others[0]].value) || 0);
  const secondCurrent = Math.max(0, Number(fields[others[1]].value) || 0);
  const otherTotal = firstCurrent + secondCurrent;
  const firstRatio = otherTotal > 0 ? firstCurrent / otherTotal : 0.5;

  let firstValue = Math.round(remaining * firstRatio);
  let secondValue = remaining - firstValue;

  if (firstValue < mins[others[0]]) {
    firstValue = mins[others[0]];
    secondValue = remaining - firstValue;
  }
  if (secondValue < mins[others[1]]) {
    secondValue = mins[others[1]];
    firstValue = remaining - secondValue;
  }

  fields[changedKey].value = String(Math.round(changedValue));
  fields[others[0]].value = String(Math.round(firstValue));
  fields[others[1]].value = String(100 - Number(fields[changedKey].value) - Number(fields[others[0]].value));
  updateSplitRatioTotal();
  isBalancingSplitRatios = false;
}

function updateSplitRatioTotal() {
  const totalEl = qs("#split-ratio-total");
  if (!totalEl) return;
  const total = ["train", "val", "test"].reduce((sum, key) => {
    return sum + (Number(qs(`#input-ratio-${key}`)?.value) || 0);
  }, 0);
  totalEl.textContent = `${total}%`;
  totalEl.classList.toggle("is-valid", total === 100);
  totalEl.classList.toggle("is-invalid", total !== 100);
}

function clampNumber(value, min, max) {
  const normalized = Number.isFinite(value) ? value : min;
  return Math.min(max, Math.max(min, normalized));
}

function bindAugmentationActions() {
  const controls = [
    "#aug-light-brightness",
    "#aug-light-contrast",
    "#aug-light-shadow",
    "#aug-weather-rain",
    "#aug-weather-fog",
    "#aug-motion-blur",
    "#aug-camera-noise",
    "#aug-camera-perspective",
    "#aug-preview-select-img"
  ];
  controls.forEach((selector) => {
    qs(selector)?.addEventListener("input", triggerAugPreview);
    qs(selector)?.addEventListener("change", triggerAugPreview);
  });

  qsa("[data-aug-preset]").forEach((button) => {
    button.addEventListener("click", () => applyAugmentationPreset(button.dataset.augPreset));
  });

  qs("#btn-apply-aug")?.addEventListener("click", async () => {
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/apply-augmentation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_split: "train",
          multiplier: Number(qs("#aug-multiplier").value || 1),
          config: getAugmentationConfig()
        })
      });
      showToast(data.message || "物理擴充完成");
      await openProject(appState.currentProjectId, { stayOnPage: true });
    } catch (err) {
      showToast(`物理擴充失敗：${err.message}`);
    }
  });
}

function applyAugmentationPreset(presetName) {
  const preset = augmentationPresets[presetName];
  if (!preset) return;
  qs("#aug-light-brightness").checked = Math.abs(preset.brightness) > 0;
  qs("#aug-light-contrast").checked = Math.abs(preset.contrast) > 0;
  qs("#aug-light-shadow").checked = preset.shadow;
  qs("#aug-weather-rain").checked = Math.abs(preset.rain) > 0;
  qs("#aug-weather-fog").checked = Math.abs(preset.fog) > 0;
  qs("#aug-motion-blur").checked = Math.abs(preset.motionBlur) > 0;
  qs("#aug-camera-noise").checked = Math.abs(preset.noise) > 0;
  qs("#aug-camera-perspective").checked = Math.abs(preset.perspective) > 0;

  qsa("[data-aug-preset]").forEach((button) => {
    button.classList.toggle("active", button.dataset.augPreset === presetName);
  });
  triggerAugPreview();
}

function getAugmentationConfig() {
  return {
    light: {
      brightness: qs("#aug-light-brightness").checked ? fixedAugmentationValues.brightness : 0,
      contrast: qs("#aug-light-contrast").checked ? fixedAugmentationValues.contrast : 0,
      shadow: qs("#aug-light-shadow").checked
    },
    weather: {
      rain: qs("#aug-weather-rain").checked ? fixedAugmentationValues.rain : 0,
      fog: qs("#aug-weather-fog").checked ? fixedAugmentationValues.fog : 0
    },
    motion: {
      motion_blur: qs("#aug-motion-blur").checked ? fixedAugmentationValues.motionBlur : 0
    },
    camera: {
      noise: qs("#aug-camera-noise").checked ? fixedAugmentationValues.noise : 0,
      perspective: qs("#aug-camera-perspective").checked ? fixedAugmentationValues.perspective : 0
    }
  };
}

async function triggerAugPreview() {
  const status = getProjectStatus(appState.currentProject);
  const filename = qs("#aug-preview-select-img")?.value;
  if (!status.hasProject || !filename) return;
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/augment-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, config: getAugmentationConfig() })
    });
    const img = qs("#aug-preview-img");
    const placeholder = qs("#aug-preview-placeholder");
    if (img) {
      img.src = data.preview;
      img.style.display = "block";
    }
    if (placeholder) placeholder.style.display = "none";
  } catch (err) {
    const img = qs("#aug-preview-img");
    const placeholder = qs("#aug-preview-placeholder");
    if (img) img.style.display = "none";
    if (placeholder) {
      placeholder.style.display = "block";
      placeholder.textContent = `預覽失敗：${err.message}`;
    }
  }
}

function bindTrainingActions() {
  qs("#btn-start-train")?.addEventListener("click", async () => {
    const status = getProjectStatus(appState.currentProject);
    if (!status.trainReady) {
      showToast("目前尚未滿足訓練條件");
      return;
    }
    try {
      await apiFetch(`/api/projects/${appState.currentProjectId}/train/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: qs("#train-model").value,
          epochs: Number(qs("#train-epochs").value),
          batch_size: Number(qs("#train-batch").value),
          imgsz: Number(qs("#train-imgsz").value),
          lr0: Number(qs("#train-lr0").value),
          device: qs("#train-device").value
        })
      });
      startMonitorWebSocket();
      showToast("訓練已啟動");
    } catch (err) {
      showToast(`啟動訓練失敗：${err.message}`);
    }
  });

  qs("#btn-stop-train")?.addEventListener("click", async () => {
    try {
      await apiFetch(`/api/projects/${appState.currentProjectId}/train/stop`, { method: "POST" });
      showToast("已送出停止訓練要求");
    } catch (err) {
      showToast(`停止訓練失敗：${err.message}`);
    }
  });
}

async function checkCurrentTrainStatus() {
  if (!appState.currentProjectId) return;
  try {
    appState.trainingStatus = await apiFetch(`/api/projects/${appState.currentProjectId}/train/status`);
    if (appState.trainingStatus.status === "training") startMonitorWebSocket();
  } catch {
    appState.trainingStatus = null;
  }
}

function startMonitorWebSocket() {
  if (!appState.currentProjectId) return;
  if (appState.wsConn) appState.wsConn.close();
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  appState.wsConn = new WebSocket(`${protocol}//${window.location.host}/api/projects/${appState.currentProjectId}/monitor`);
  appState.wsConn.onmessage = (event) => {
    appState.trainingStatus = JSON.parse(event.data);
    renderTrainingMonitor();
    updateActionAvailability(getProjectStatus(appState.currentProject));
    if (appState.trainingStatus.status !== "training") {
      appState.wsConn.close();
    }
  };
  appState.wsConn.onerror = () => showToast("Training monitor WebSocket 發生錯誤");
}

function bindExportActions() {
  qs("#btn-export-pt")?.addEventListener("click", exportModel);
  qs("#btn-export-onnx")?.addEventListener("click", exportModel);
  qs("#btn-export-report")?.addEventListener("click", generateReport);
}

async function exportModel() {
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/export`);
    showToast(`匯出完成：${data.onnx_path || data.pt_path || "exported"}`);
  } catch (err) {
    showToast(`匯出失敗：${err.message}`);
  }
}

function generateReport() {
  const project = appState.currentProject;
  if (!project) return;
  const status = getProjectStatus(project);
  const report = `# Vision Training Studio Report

- Project: ${project.project_name}
- Task type: ${project.task_type}
- Images: ${status.imageCount}
- Annotation progress: ${status.annotatedCount}/${status.imageCount}
- LabelMe backend: Connected
- Split: ${status.splitComplete ? "Ready" : "Not ready"}
- Training: ${status.trainingLabel}
`;
  const blob = new Blob([report], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${project.project_name || "vision_training"}_report.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function bindLabelMeActions() {
  qs("#btn-open-labelme")?.addEventListener("click", openExternalLabelMe);
  qs("#btn-refresh-labelme")?.addEventListener("click", async () => {
    await syncLabelMeLabels(true);
  });
  qs("#btn-sync-labelme")?.addEventListener("click", () => {
    syncLabelMeLabels(false);
  });
  qs("#btn-copy-images-path")?.addEventListener("click", () => copyText(qs("#labelme-images-path")?.textContent));
  qs("#btn-copy-json-path")?.addEventListener("click", () => copyText(qs("#labelme-json-path")?.textContent));
  qs("#btn-copy-labelme-command")?.addEventListener("click", () => copyText(qs("#labelme-command")?.textContent));

  // 轉換按鈕事件綁定
  const converters = {
    "#btn-convert-yolo-det": "yolo_detection",
    "#btn-convert-yolo-seg": "yolo_segmentation",
    "#btn-convert-coco": "coco",
    "#btn-convert-mask": "semantic_mask"
  };

  Object.entries(converters).forEach(([id, type]) => {
    qs(id)?.addEventListener("click", async () => {
      const btn = qs(id);
      btn.disabled = true;
      showToast(`正在將標註轉換為 ${type}...`);
      try {
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/convert`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ export_type: type })
        });
        showToast(`轉換完成！成功處理 ${data.converted_count} 個檔案。`);
        await openProject(appState.currentProjectId);
      } catch (err) {
        showToast(`轉換失敗：${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });

  // 僅顯示異常項目的核取方塊監聽
  qs("#chk-show-issues-only")?.addEventListener("change", () => {
    renderLabelMeManager(getProjectStatus(appState.currentProject));
  });

  // 標註檔案拖曳與點選上傳區 (原生實作，避免 Dropzone 並行發送多個請求導致的寫入鎖定與效能衝突)
  const annoDropZone = qs("#annotations-drop-zone");
  const inputAnnoFile = qs("#input-annotations-file");

  async function handleAnnotationUpload(files) {
    if (!appState.currentProjectId) {
      showToast("請先載入或建立專案！");
      return;
    }

    const validFiles = files.filter(file => {
      const name = file.name.toLowerCase();
      return name.endsWith(".json") || name.endsWith(".txt");
    });

    if (validFiles.length === 0) {
      showToast("無有效的 .json 或 .txt 標註檔！");
      return;
    }

    const batchSize = 800;
    const batches = [];
    for (let i = 0; i < validFiles.length; i += batchSize) {
      batches.push(validFiles.slice(i, i + batchSize));
    }

    showToast(`開始導入共 ${validFiles.length} 個標註檔案（分 ${batches.length} 批上傳中）...`);
    
    let importedJsons = 0;
    let importedTxts = 0;

    try {
      for (let k = 0; k < batches.length; k++) {
        const currentBatch = batches[k];
        showToast(`正在上傳第 ${k + 1}/${batches.length} 批標註檔案 (${currentBatch.length} 個)...`);
        
        const formData = new FormData();
        currentBatch.forEach(file => {
          formData.append("files", file, file.name);
        });

        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-annotations`, {
          method: "POST",
          body: formData
        });
        
        importedJsons += data.imported_jsons || 0;
        importedTxts += data.imported_txts || 0;
      }
      
      showToast(`所有標註檔案匯入完成！共匯入 ${importedJsons} 個 JSON 與 ${importedTxts} 個 TXT 檔案。`);
      await openProject(appState.currentProjectId);
    } catch (err) {
      showToast(`標註檔案匯入失敗：${err.message}`);
    }
  }

  if (annoDropZone && inputAnnoFile) {
    inputAnnoFile.style.display = "none";
    
    // 確保銷毀 Dropzone 實體以避免衝突
    if (annoDropZone.dropzone) {
      annoDropZone.dropzone.destroy();
    }

    // 點擊觸發檔案選擇
    annoDropZone.addEventListener("click", () => {
      inputAnnoFile.click();
    });

    // 點選檔案改變事件
    inputAnnoFile.addEventListener("change", async (event) => {
      const files = [...(event.target.files || [])];
      if (files.length === 0) return;
      await handleAnnotationUpload(files);
      inputAnnoFile.value = "";
    });

    // 拖曳 hover 狀態處理
    ["dragenter", "dragover"].forEach((eventName) => {
      annoDropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        annoDropZone.classList.add("dz-drag-hover");
      }, true);
    });

    ["dragleave", "dragend"].forEach((eventName) => {
      annoDropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        annoDropZone.classList.remove("dz-drag-hover");
      }, true);
    });

    // 拖曳放下事件 (支援資料夾深度遍歷與自動過濾)
    annoDropZone.addEventListener("drop", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      annoDropZone.classList.remove("dz-drag-hover");

      if (!appState.currentProjectId) {
        showToast("請先載入或建立專案！");
        return;
      }

      showToast("正在掃描拖入的項目（支援資料夾遞迴）...");
      try {
        const files = await collectDroppedFiles(e.dataTransfer);
        await handleAnnotationUpload(files);
      } catch (err) {
        showToast(`讀取拖入項目失敗：${err.message}`);
      }
    }, true);
  }
}

async function openExternalLabelMe() {
  if (!appState.currentProjectId) {
    showToast("請先載入或建立專案。");
    return;
  }
  const btn = qs("#btn-open-labelme");
  if (btn) btn.disabled = true;
  showToast("正在開啟外部 LabelMe...");
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/open`, { method: "POST" });
    showToast(data.message || "LabelMe 已啟動。");
  } catch (err) {
    const message = err.message === "Not Found"
      ? "LabelMe 啟動 API 尚未載入，請重啟 FastAPI 後端後再試。"
      : `LabelMe 啟動失敗：${err.message}`;
    showToast(message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function syncLabelMeLabels(silent = false) {
  const btn = qs("#btn-sync-labelme");
  if (btn) btn.disabled = true;
  if (!silent) showToast("正在掃描與同步 LabelMe JSON 標註檔...");
  
  try {
    const report = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/sync`, { method: "POST" });
    
    appState.labelme.jsonCount = report.annotated;
    appState.labelme.missingJson = report.missing_json;
    appState.labelme.invalidJson = report.corrupted_json;
    appState.labelme.totalImages = report.total_images;
    appState.labelme.synced = true;
    appState.labelme.completionRate = report.total_images > 0 ? Math.round((report.annotated / report.total_images) * 100) : 0;
    appState.labelme.unknownClasses = report.unknown_classes;
    
    await openProject(appState.currentProjectId, { stayOnPage: true });
    if (!silent) showToast("同步完成！");
  } catch (err) {
    showToast(`同步失敗：${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function copyText(text) {
  if (!text || text === "尚未載入專案") return;
  try {
    await navigator.clipboard.writeText(text);
    showToast("路徑已複製");
  } catch {
    showToast("無法使用剪貼簿，請手動複製路徑");
  }
}

function updateLabelMeState() {
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

function getProjectStatus(project) {
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

function renderAll() {
  const status = getProjectStatus(appState.currentProject);
  renderDashboard();
  renderProjectSummary(status);
  renderNextActions(status);
  renderWarnings(status);
  renderPageGuards(appState.currentPage, status);
  renderDatasetPage(status);
  renderLabelMeManager(status);
  renderSplitPage(status);
  renderAugmentationPage(status);
  renderTrainingMonitor();
  renderEvaluationPage(status);
  updateActionAvailability(status);
  applyLanguage(appState.settings.language);
}

function renderDashboard() {
  const status = getProjectStatus(appState.currentProject);
  renderDashboardAlerts(status);
  renderKpis(status);
  renderControlCards(status);
  renderRecentProjects(appState.projects);
  renderActivity(status);
}

function renderDashboardAlerts(status) {
  const guards = [];
  if (!status.hasProject) {
    guards.push(statusGuard("info", "尚未載入專案", ["請先建立或開啟專案。"], "前往 Projects 建立新專案，或從 Recent Projects 開啟舊專案。"));
  } else if (!status.hasDataset) {
    guards.push(statusGuard("warning", "專案已載入，但尚未匯入資料", ["Dataset image count 為 0。"], "前往 Dataset 匯入圖片資料夾或影片抽幀。"));
  }
  guards.push(statusGuard("info", "LabelMe 狀態", ["UI Ready", "Backend Connected", "可掃描 raw/annotations/labelme/*.json。"], "前往 LabelMe 頁面同步 JSON，完成後可預覽與轉換。"));
  setHTML("#dashboard-alerts", guards.join(""));
}

function renderKpis(status) {
  const items = [
    ["Project", status.projectName],
    ["Images", status.imageCount],
    ["LabelMe JSON", `${status.labelme.jsonCount}/${status.imageCount}`],
    ["Split", status.splitComplete ? "Ready" : "Not ready"]
  ];
  setHTML("#dashboard-kpis", items.map(([label, value]) => `
    <div class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join(""));
}

function renderControlCards(status) {
  const cards = [
    {
      icon: "fa-folder-tree",
      title: "Project",
      badge: status.hasProject ? "Loaded" : "No project",
      badgeClass: status.hasProject ? "success" : "warning",
      desc: "建立、開啟與管理視覺訓練專案。",
      stats: [["Task", status.taskType], ["Classes", status.classNames.length]],
      progress: status.hasProject ? 100 : 0,
      actions: [
        button("Projects", "projects", "primary"),
        button("Browse History", "history", "secondary")
      ]
    },
    {
      icon: "fa-images",
      title: "Dataset",
      badge: status.hasDataset ? "Imported" : "No data",
      badgeClass: status.hasDataset ? "success" : "warning",
      desc: "管理圖片、影片抽幀與品質檢查。",
      stats: [["Images", status.imageCount], ["Health", appState.currentProject?.dataset_health?.score ?? "--"]],
      progress: status.hasDataset ? 100 : 0,
      actions: [button("Import Images", "dataset", "primary"), button("Quality Check", "dataset", "secondary")]
    },
    {
      icon: "fa-pen-nib",
      title: "LabelMe",
      badge: "Backend Connected",
      badgeClass: "success",
      desc: "管理 LabelMe JSON 工作流，取代舊版 Canvas bbox 標註主入口。",
      stats: [["JSON", status.labelme.jsonCount], ["Missing", status.labelme.missingJson]],
      progress: status.labelme.completionRate,
      actions: [button("Open Manager", "labelme", "primary"), button("Sync JSON", "labelme", "secondary")]
    },
    {
      icon: "fa-code-branch",
      title: "Split",
      badge: status.splitComplete ? "Ready" : "Not split",
      badgeClass: status.splitComplete ? "success" : "warning",
      desc: "建立 Train / Val / Test，避免資料外洩。",
      stats: [["Train", status.splitCounts.train], ["Val", status.splitCounts.val], ["Test", status.splitCounts.test]],
      progress: status.splitComplete ? 100 : 0,
      actions: [button("Configure Split", "split", "primary"), button("Run Split", "split", "secondary")]
    },
    {
      icon: "fa-wand-magic-sparkles",
      title: "Augmentation",
      badge: appState.currentProject?.augmentation_config ? "Configured" : "Not configured",
      badgeClass: appState.currentProject?.augmentation_config ? "info" : "warning",
      desc: "設定物理擴充並預覽結果。",
      stats: [["Requires", "Split"], ["Target", "Train"]],
      progress: status.splitComplete ? 60 : 0,
      actions: [button("Configure", "augmentation", "primary"), button("Preview", "augmentation", "secondary")]
    },
    {
      icon: "fa-microchip",
      title: "Training",
      badge: status.trainReady ? "Ready" : "Not ready",
      badgeClass: status.trainReady ? "success" : "danger",
      desc: "設定模型與啟動訓練。LabelMe sync 完成前不能開始。",
      stats: [["Status", status.trainingLabel], ["Blockers", status.blockers.length]],
      progress: status.trainReady ? 100 : 25,
      actions: [button("Configure", "training", "primary"), disabledButton("Start Training")]
    },
    {
      icon: "fa-chart-line",
      title: "Evaluation",
      badge: status.bestModelExists ? "Available" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      desc: "查看 mAP、IoU、failure cases 與模型品質。",
      stats: [["mAP", "--"], ["IoU", "--"]],
      progress: status.bestModelExists ? 100 : 0,
      actions: [button("View Evaluation", "evaluation", "primary")]
    },
    {
      icon: "fa-file-export",
      title: "Export",
      badge: status.bestModelExists ? "Exportable" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      desc: "匯出 PT、ONNX、報告，TensorRT 後續擴充。",
      stats: [["ONNX", "Supported"], ["TensorRT", "Pending"]],
      progress: status.bestModelExists ? 100 : 0,
      actions: [button("Open Export", "export", "primary")]
    }
  ];

  setHTML("#control-cards", cards.map(renderControlCard).join(""));
}

function renderControlCard(card) {
  return `
    <article class="control-card">
      <div class="card-heading"><i class="fa-solid ${card.icon}"></i><h3>${escapeHtml(card.title)}</h3></div>
      <span class="badge badge-${card.badgeClass}">${escapeHtml(card.badge)}</span>
      <p>${escapeHtml(card.desc)}</p>
      <div>
        ${card.stats.map((item) => `<div class="card-stat"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`).join("")}
        <div class="progress-block" style="margin-top:10px">
          <div class="progress-track"><div class="progress-fill" style="width:${Number(card.progress) || 0}%"></div></div>
        </div>
      </div>
      <div class="card-actions">${card.actions.join("")}</div>
    </article>
  `;
}

function button(label, page, type) {
  return `<button class="btn btn-${type}" data-nav="${page}">${escapeHtml(label)}</button>`;
}

function disabledButton(label) {
  return `<button class="btn btn-disabled" disabled>${escapeHtml(label)}</button>`;
}

function renderProjectSummary(status) {
  setHTML("#project-summary", `
    <div class="path-list">
      <div class="path-row"><span>Name</span><code>${escapeHtml(status.projectName)}</code></div>
      <div class="path-row"><span>Task</span><code>${escapeHtml(status.taskType)}</code></div>
      <div class="path-row"><span>Images</span><code>${status.imageCount}</code></div>
      <div class="path-row"><span>Annotated</span><code>${status.annotatedCount}/${status.imageCount}</code></div>
      <div class="path-row"><span>LabelMe</span><code>Backend Connected</code></div>
      <div class="path-row"><span>Split</span><code>${status.splitComplete ? "Ready" : "Not ready"}</code></div>
      <div class="path-row"><span>Training</span><code>${escapeHtml(status.trainingLabel)}</code></div>
    </div>
  `);
}

function renderNextActions(status) {
  const actions = [];
  if (!status.hasProject) actions.push("前往 Projects 建立或開啟專案。");
  if (status.hasProject && !status.hasDataset) actions.push("前往 Dataset 匯入圖片或影片抽幀。");
  if (status.hasDataset && !status.labelme.synced) actions.push("前往 LabelMe 同步 JSON，確認標註進度。");
  if (status.hasDataset && !status.splitComplete) actions.push("前往 Split 建立 Train / Val / Test。");
  if (status.trainReady) actions.push("前往 Training 啟動訓練。");
  if (actions.length === 0) actions.push("目前沒有必要動作。");
  setHTML("#next-actions-list", actions.map((action) => `<li>${escapeHtml(action)}</li>`).join(""));
}

function renderWarnings(status) {
  const warnings = [];
  if (!status.labelme.backendReady) warnings.push("LabelMe backend sync 尚未連線。");
  if (!status.trainReady) warnings.push("Start Training 已依狀態 disabled。");
  if (!status.hasProject) warnings.push("尚未載入專案時，頁面可瀏覽但操作會被停用。");
  setHTML("#warning-list", warnings.map((item) => `<div class="activity-item">${escapeHtml(item)}</div>`).join(""));
}

function renderRecentProjects(projects) {
  const subset = (projects || []).slice(0, 5);
  setHTML("#recent-projects-list", renderProjectList(subset, { includeDelete: false }));
  bindProjectListButtons();
}

function renderActivity(status) {
  const items = [
    `Frontend phase: Dashboard Control Center`,
    `LabelMe: Backend Connected`,
    `Current page: ${appState.currentPage}`,
    `Training status: ${status.trainingLabel}`
  ];
  setHTML("#recent-activity-list", items.map((item) => `<div class="activity-item">${escapeHtml(item)}</div>`).join(""));
}

function renderPageGuards(pageId, status) {
  const guards = {
    dataset: [],
    labelme: [],
    split: [],
    augmentation: [],
    training: [],
    evaluation: [],
    export: []
  };

  if (!status.hasProject) {
    const guard = statusGuard("warning", "尚未載入專案", ["此頁可瀏覽，但操作已停用。"], "前往 Projects 建立或開啟專案。");
    Object.keys(guards).forEach((key) => guards[key].push(guard));
  }
  if (status.hasProject && !status.hasDataset) {
    guards.labelme.push(statusGuard("warning", "尚未匯入資料集", ["Images folder 目前沒有圖片。"], "前往 Dataset 匯入圖片或影片抽幀。"));
    guards.split.push(statusGuard("warning", "尚未匯入資料集", ["不能建立 Train / Val / Test。"], "先完成 Dataset 匯入。"));
    guards.training.push(statusGuard("danger", "目前無法開始訓練", ["尚未匯入資料集。"], "前往 Dataset 匯入圖片。"));
  }
  if (status.hasDataset && !status.labelme.synced) {
    guards.training.push(statusGuard("danger", "目前無法開始訓練", ["尚未同步 LabelMe 標註。"], "前往 LabelMe 頁同步 JSON，再轉換為訓練格式。"));
    guards.split.push(statusGuard("info", "LabelMe 尚未同步", ["此階段仍可設定 split UI，但正式訓練應等待 LabelMe JSON 轉換完成。"], "前往 LabelMe 頁同步 JSON 與執行轉換。"));
  }
  if (status.hasDataset && !status.splitComplete) {
    guards.training.push(statusGuard("danger", "目前無法開始訓練", ["尚未建立 Train / Val / Test。"], "前往 Split 建立資料分散。"));
    guards.augmentation.push(statusGuard("warning", "尚未完成 split", ["套用 augmentation 前需要知道 target split。"], "前往 Split 建立 Train / Val / Test。"));
  }
  if (!status.bestModelExists) {
    guards.evaluation.push(statusGuard("warning", "目前沒有可評估模型", ["尚未完成訓練或尚未產生 best model。"], "完成訓練後再查看 mAP / IoU。"));
    guards.export.push(statusGuard("warning", "目前沒有可匯出模型", ["尚未找到最佳模型權重。"], "完成訓練後再匯出 PT / ONNX。"));
  }

  // 取得當前活動頁面的限制警告
  const activeGuards = guards[pageId] || [];
  const container = qs("#page-guards-container");
  const section = qs("#section-page-guards");
  
  if (container && section) {
    if (activeGuards.length > 0) {
      section.style.display = "block";
      setHTML("#page-guards-container", activeGuards.join(""));
      // 根據當前活動頁面動態更新標題
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

function renderDatasetPage(status) {
  const project = appState.currentProject;
  const rawImages = (project?.images || []).filter((img) => !img.is_augmented);
  const zipPath = status.datasetPath ? `${status.datasetPath}/packages/zip` : "尚未載入專案";
  setText("#dataset-zip-storage-path", zipPath);

  // 渲染資料集類別編輯清單
  const classesListBox = qs("#dataset-classes-list-box");
  if (classesListBox) {
    if (!appState.currentProjectClasses && project) {
      appState.currentProjectClasses = [...(project.class_names || [])];
    }
    renderDatasetClassesEditList();
  }

  const query = qs("#search-image")?.value?.toLowerCase() || "";
  const filter = qs("#filter-status")?.value || "all";
  const filtered = rawImages.filter((img) => {
    const matchesQuery = img.filename.toLowerCase().includes(query);
    const matchesFilter = filter === "all" || img.status === filter;
    return matchesQuery && matchesFilter;
  });
  setText("#dataset-count-total", filtered.length);
  setText("#health-score-val", project?.dataset_health?.score ?? "--");
  if (!status.hasProject) {
    setHTML("#dataset-thumbnails", `<div class="empty-state">請先載入專案。</div>`);
    return;
  }
  if (filtered.length === 0) {
    setHTML("#dataset-thumbnails", `<div class="empty-state">目前沒有符合條件的圖片。</div>`);
    return;
  }
  const visibleImages = filtered.slice(0, appState.datasetVisibleLimit);
  const hiddenCount = Math.max(0, filtered.length - visibleImages.length);
  const cards = visibleImages.map((img) => `
    <article class="thumb-card">
      <div class="thumb-image-frame">
        <img
          src="/api/projects/${encodeURIComponent(appState.currentProjectId)}/thumbnails/${encodeURIComponent(img.filename)}"
          loading="lazy"
          decoding="async"
          fetchpriority="low"
          alt="${escapeHtml(img.filename)}"
        >
      </div>
      <footer>
        <strong title="${escapeHtml(img.filename)}">${escapeHtml(img.filename)}</strong>
        <span class="badge ${badgeClassForStatus(img.status)}">${escapeHtml(img.status || "unknown")}</span>
      </footer>
    </article>
  `);
  if (hiddenCount > 0) {
    cards.push(`
      <button type="button" class="load-more-card" id="btn-load-more-images">
        <strong>Load more images</strong>
        <span>${visibleImages.length} / ${filtered.length} shown</span>
      </button>
    `);
  }
  setHTML("#dataset-thumbnails", cards.join(""));
}

function renderDatasetClassesEditList() {
  const box = qs("#dataset-classes-list-box");
  if (!box) return;
  const classes = appState.currentProjectClasses || [];
  if (classes.length === 0) {
    box.innerHTML = '<span class="empty-class-list">目前無類別。請新增類別。</span>';
    return;
  }
  box.innerHTML = classes.map(cls => `
    <span class="class-chip">
      ${escapeHtml(cls)}
      <button type="button" data-remove-dataset-class="${escapeHtml(cls)}" style="border:none;background:none;cursor:pointer;color:var(--text-muted);">&times;</button>
    </span>
  `).join("");
}

function badgeClassForStatus(status) {
  if (status === "annotated") return "badge-success";
  if (status === "flagged") return "badge-warning";
  if (status === "skipped") return "badge-danger";
  return "badge-muted";
}

function renderLabelMeManager(status) {
  const datasetPath = status.datasetPath || "";
  const imagesPath = datasetPath ? `${datasetPath}/raw/images` : "尚未載入專案";
  const jsonPath = datasetPath ? `${datasetPath}/raw/annotations/labelme` : "尚未載入專案";
  const outputPath = datasetPath ? `${datasetPath}/raw/labels` : "尚未載入專案";
  setText("#labelme-images-path", imagesPath);
  setText("#labelme-json-path", jsonPath);
  setText("#labelme-output-path", outputPath);
  setText("#labelme-classes", status.classNames.length ? status.classNames.join(", ") : "--");
  setText("#labelme-command", datasetPath ? `labelme "${imagesPath}" --output "${jsonPath}"` : "尚未載入專案");
  const metrics = [
    ["Total images", status.labelme.totalImages],
    ["LabelMe JSON files", status.labelme.jsonCount],
    ["Missing JSON", status.labelme.missingJson],
    ["Empty JSON", status.labelme.emptyJson],
    ["Unknown labels", status.labelme.unknownLabels],
    ["Invalid JSON", status.labelme.invalidJson]
  ];
  setHTML("#labelme-progress-grid", metrics.map(([label, value]) => `
    <div class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join(""));
  setText("#labelme-completion-text", `${status.labelme.completionRate}%`);
  const bar = qs("#labelme-completion-bar");
  if (bar) bar.style.width = `${status.labelme.completionRate}%`;
  const rawImages = (appState.currentProject?.images || []).filter((img) => !img.is_augmented);
  if (rawImages.length === 0) {
    setHTML("#labelme-check-table", `
      <tr>
        <td colspan="5" style="text-align:center;">無資料。請先到 Dataset 頁面匯入圖片。</td>
      </tr>
    `);
    return;
  }

  const isSegmentationTask = String(status.taskType || "").toLowerCase().includes("segmentation");
  const hasSegmentationBbox = (img) => isSegmentationTask && (img.annotations || []).some((ann) => ann.type === "bbox");
  const showIssuesOnly = qs("#chk-show-issues-only")?.checked ?? true;
  const filteredImages = showIssuesOnly 
    ? rawImages.filter(img => img.status !== "annotated" || hasSegmentationBbox(img))
    : rawImages;

  if (filteredImages.length === 0) {
    setHTML("#labelme-check-table", `
      <tr>
        <td colspan="5" style="text-align:center; padding: 24px; color: var(--text-muted);">
          <i class="fa-solid fa-circle-check" style="color: var(--success); margin-right: 6px; font-size: 1.1rem;"></i> 所有檔案皆已正確標註並通過檢查。
        </td>
      </tr>
    `);
    return;
  }

  const rows = filteredImages.map(img => {
    let statusText = "Unannotated";
    let issueText = "Missing JSON";
    let fixText = "Use LabelMe to annotate";
    let rowClass = "row-missing";
    
    const needsPolygon = hasSegmentationBbox(img);

    if (img.status === "annotated") {
      statusText = "Annotated";
      issueText = "None";
      fixText = "None";
      rowClass = "row-success";
    } else if (img.status === "flagged") {
      statusText = "Flagged";
      issueText = "Flagged for review";
      fixText = "Review annotations in LabelMe";
      rowClass = "row-warning";
    } else if (img.status === "skipped") {
      statusText = "Skipped";
      issueText = "Skipped";
      fixText = "None";
      rowClass = "row-muted";
    }

    if (needsPolygon) {
      statusText = "Needs polygon";
      issueText = "Segmentation project contains rectangle / bbox shapes";
      fixText = "Open LabelMe and redraw these labels with polygon";
      rowClass = "row-warning";
    }
    
    return `
      <tr class="${rowClass}" data-preview-img="${escapeHtml(img.filename)}" style="cursor:pointer;">
        <td><code>${escapeHtml(img.filename.replace(/\.[^/.]+$/, ".json"))}</code></td>
        <td>${escapeHtml(img.filename)}</td>
        <td><span class="badge ${needsPolygon ? "badge-warning" : badgeClassForStatus(img.status)}">${statusText}</span></td>
        <td>${issueText}</td>
        <td>${fixText}</td>
      </tr>
    `;
  });
  setHTML("#labelme-check-table", rows.join(""));
  
  qsa("#labelme-check-table tr").forEach(row => {
    row.addEventListener("click", () => {
      const filename = row.dataset.previewImg;
      if (filename) previewLabelMeImage(filename);
    });
  });
}

async function previewLabelMeImage(filename) {
  const panel = qs("#labelme-preview-panel");
  if (!panel) return;
  
  panel.innerHTML = `
    <div class="preview-placeholder">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <p>正在載入 ${escapeHtml(filename)} 預覽...</p>
    </div>
  `;
  
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/preview/${filename}`);
    
    panel.innerHTML = `
      <div style="position:relative; width:100%; height:100%; display:flex; align-items:center; justify-content:center;">
        <canvas id="lbl-preview-canvas" style="max-width:100%; max-height:100%; object-fit:contain;"></canvas>
      </div>
    `;
    
    const canvas = qs("#lbl-preview-canvas");
    const ctx = canvas.getContext("2d");
    
    const img = new Image();
    img.src = `/api/projects/${appState.currentProjectId}/images/${filename}`;
    
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
      
      const shapes = data.shapes || [];
      shapes.forEach(shape => {
        const pts = shape.points || [];
        if (pts.length < 2) return;
        
        ctx.strokeStyle = colorForLabel(shape.label);
        ctx.lineWidth = Math.max(3, img.width / 300);
        ctx.fillStyle = "rgba(0, 210, 211, 0.15)";
        
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i][0], pts[i][1]);
        }
        
        if (shape.shape_type === "rectangle") {
          ctx.closePath();
          const w = pts[1][0] - pts[0][0];
          const h = pts[1][1] - pts[0][1];
          ctx.strokeRect(pts[0][0], pts[0][1], w, h);
          ctx.fillRect(pts[0][0], pts[0][1], w, h);
        } else {
          ctx.closePath();
          ctx.stroke();
          ctx.fill();
        }
        
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = `bold ${Math.max(16, img.width / 40)}px Inter`;
        ctx.fillText(shape.label, pts[0][0], pts[0][1] - 8);
      });
    };
  } catch (err) {
    panel.innerHTML = `
      <div class="preview-placeholder text-red">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <p>載入預覽失敗：${escapeHtml(err.message)}</p>
      </div>
    `;
  }
}

function renderSplitPage(status) {
  if (appState.currentProject?.split_report) {
    renderSplitReportUI(appState.currentProject.split_report);
  } else if (!status.splitComplete) {
    setHTML("#split-report-card", "");
  }
}

function renderSplitReportUI(report) {
  if (!report) return;
  setHTML("#split-report-card", `
    <div class="status-guard ${report.score >= 80 ? "success" : report.score >= 50 ? "warning" : "danger"}">
      <div class="guard-title">Split quality score: ${escapeHtml(report.score ?? "--")}</div>
      <ul>${(report.warnings || ["沒有明顯警告"]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </div>
  `);
}

function renderAugmentationPage(status) {
  const select = qs("#aug-preview-select-img");
  if (!select) return;
  const options = (appState.currentProject?.images || [])
    .filter((img) => !img.is_augmented && img.status === "annotated")
    .map((img) => `<option value="${escapeHtml(img.filename)}">${escapeHtml(img.filename)}</option>`);
  select.innerHTML = options.length ? options.join("") : `<option value="">沒有可預覽的已標註圖片</option>`;
}

function renderTrainingMonitor() {
  const status = appState.trainingStatus || {};
  setText("#train-status-label", status.status || "Idle");
  setText("#train-progress-text", `Epoch ${status.epoch || 0} / ${status.total_epochs || 0}`);
  const hw = status.hardware || {};
  setText("#hw-cpu-val", hw.cpu_usage !== undefined ? `${hw.cpu_usage}%` : "--");
  setText("#hw-ram-val", hw.ram_used !== undefined ? `${hw.ram_used} / ${hw.ram_total} MB` : "--");
  const gpu = hw.gpu || {};
  setText("#hw-gpu-val", gpu.available ? `${gpu.usage}%` : "N/A");
  setText("#hw-vram-val", gpu.available ? `${gpu.vram_used} / ${gpu.vram_total} MB` : "N/A");
  const metrics = status.metrics || [];
  setHTML("#training-metrics-list", metrics.length ? metrics.slice(-8).reverse().map((item) => `
    <div class="activity-item">Epoch ${item.epoch}: loss ${Number(item.loss || 0).toFixed(4)}, mAP50 ${Number(item.map50 || 0).toFixed(3)}</div>
  `).join("") : `<div class="empty-state">尚無訓練 metrics。</div>`);
  qs("#btn-stop-train")?.classList.toggle("hidden", status.status !== "training");
}

function renderEvaluationPage() {
  const metrics = appState.trainingStatus?.metrics || [];
  if (!metrics.length) {
    setText("#eval-map50", "--");
    setText("#eval-iou", "--");
    setText("#eval-precision", "--");
    setText("#eval-recall", "--");
    return;
  }
  const best = metrics.reduce((prev, curr) => (Number(prev.map50 || 0) > Number(curr.map50 || 0) ? prev : curr));
  setText("#eval-map50", Number(best.map50 || 0).toFixed(3));
  setText("#eval-iou", "--");
  setText("#eval-precision", Number(best.precision || 0).toFixed(3));
  setText("#eval-recall", Number(best.recall || 0).toFixed(3));
}

function updateActionAvailability(status) {
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

// Old annotation API intentionally not wired into the main UI in Phase 1.
const legacyAnnotation = {
  enabled: false,
  reason: "Replaced by LabelMe Annotation Manager in the primary workflow."
};
