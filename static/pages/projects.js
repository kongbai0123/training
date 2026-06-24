import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml } from "../utils.js";

export function initProjects() {
  qs("#btn-reload-projects")?.addEventListener("click", () => {
    eventBus.emit("reload-projects");
  });
  qs("#btn-open-create-project")?.addEventListener("click", openCreateProjectModal);
  qs("#btn-close-create-project")?.addEventListener("click", closeCreateProjectModal);
  qs("#btn-cancel-create-project")?.addEventListener("click", closeCreateProjectModal);
  qs("#project-create-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "project-create-modal") closeCreateProjectModal();
  });

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

  qs("#form-create-project")?.addEventListener("submit", createProject);

  qs("#btn-close-delete-project")?.addEventListener("click", closeDeleteProjectModal);
  qs("#btn-cancel-delete-project")?.addEventListener("click", closeDeleteProjectModal);
  qs("#delete-project-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "delete-project-modal") closeDeleteProjectModal();
  });
  qs("#btn-confirm-delete-project")?.addEventListener("click", confirmDeleteProject);

  eventBus.on("render-recent-projects-list", (subset) => {
    setHTML("#recent-projects-list", renderProjectList(subset, { includeDelete: false, compact: true }));
    bindProjectListButtons();
  });
  eventBus.on("render-project-history-modal", () => {
    setHTML("#modal-project-list", renderProjectList(appState.projects, { includeDelete: false, showFiles: true }));
    bindProjectListButtons();
  });
  eventBus.on("open-create-project-modal", openCreateProjectModal);

  renderNewProjectClassList();
}

export function renderProjectsPage() {
  const html = renderProjectList(appState.projects, { includeDelete: true, showFiles: true });
  setHTML("#project-history-list", html);
  setHTML("#history-list", html);
  setHTML("#modal-project-list", renderProjectList(appState.projects, { includeDelete: false, showFiles: true }));
  bindProjectListButtons();
}

export function renderProjectList(projects, options = {}) {
  if (!projects || projects.length === 0) {
    return `<div class="empty-state">目前沒有專案。請使用 New Project 建立新專案。</div>`;
  }

  return projects.map((project) => renderProjectCard(project, options)).join("");
}

function renderProjectCard(project, options = {}) {
  const progress = project.annotation_progress || {};
  const files = project.file_summary || {};
  const updatedAt = formatDate(project.updated_at);
  const progressText = progress.total
    ? `${progress.annotated || 0}/${progress.total || 0} annotated`
    : "No images imported";
  const classNames = Array.isArray(project.class_names) ? project.class_names : [];

  return `
    <article class="project-history-card ${options.compact ? "compact" : ""}">
      <div class="project-history-main">
        <div>
          <div class="project-history-title-row">
            <h3>${escapeHtml(project.project_name || project.project_id)}</h3>
            <span class="badge badge-muted">${escapeHtml(project.task_type || "--")}</span>
          </div>
          <p>${escapeHtml(progressText)} · Updated ${escapeHtml(updatedAt || "--")}</p>
        </div>
        <div class="button-row">
          <button class="btn btn-secondary btn-sm" data-open-project="${escapeHtml(project.project_id)}">Open</button>
          ${options.includeDelete ? `<button class="icon-btn" data-delete-project="${escapeHtml(project.project_id)}" title="Delete"><i class="fa-solid fa-trash"></i></button>` : ""}
        </div>
      </div>
      ${options.showFiles ? `
        <div class="project-file-summary">
          ${fileMetric("Images", files.images ?? progress.total ?? 0)}
          ${fileMetric("LabelMe JSON", files.labelme_json ?? 0)}
          ${fileMetric("YOLO labels", files.yolo_labels ?? 0)}
          ${fileMetric("Videos", files.videos ?? 0)}
          ${fileMetric("Split", files.split_ready ? "Ready" : "None", files.split_ready ? "success" : "muted")}
          ${fileMetric("best.pt", files.best_weights ?? 0)}
          ${fileMetric("last.pt", files.last_weights ?? 0)}
          ${fileMetric("Inference jobs", files.inference_jobs ?? 0)}
          ${fileMetric("Exports", files.exports ?? 0)}
        </div>
        <div class="project-file-details">
          <div><span>Project ID</span><code>${escapeHtml(project.project_id || "--")}</code></div>
          <div><span>Layout</span><code>${escapeHtml(files.layout_mode || "--")}</code></div>
          <div><span>Classes</span><code>${escapeHtml(classNames.length ? classNames.join(", ") : "--")}</code></div>
          <div><span>Project root</span><code>${escapeHtml(files.project_root || project.path || "--")}</code></div>
        </div>
      ` : ""}
    </article>
  `;
}

function fileMetric(label, value, badgeType = null) {
  const valueHtml = badgeType
    ? `<span class="summary-badge badge-${badgeType}">${escapeHtml(value)}</span>`
    : `<strong>${escapeHtml(value)}</strong>`;
  return `<div class="project-file-metric"><span>${escapeHtml(label)}</span>${valueHtml}</div>`;
}

export function bindProjectListButtons() {
  qsa("[data-open-project]").forEach((btn) => {
    btn.addEventListener("click", () => {
      closeHistoryModal();
      closeCreateProjectModal();
      eventBus.emit("open-project", btn.dataset.openProject);
    });
  });
  qsa("[data-delete-project]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openDeleteProjectModal(btn.dataset.deleteProject);
    });
  });
}

function openCreateProjectModal() {
  const modal = qs("#project-create-modal");
  if (!modal) return;
  modal.hidden = false;
  qs("#new-project-name")?.focus();
}

function closeCreateProjectModal() {
  const modal = qs("#project-create-modal");
  if (modal) modal.hidden = true;
}

async function createProject(event) {
  event.preventDefault();
  const name = qs("#new-project-name")?.value.trim();
  const type = qs("#new-project-type")?.value;
  const classes = [...appState.newProjectClasses];

  if (!name || classes.length === 0) {
    eventBus.emit("toast", "請輸入專案名稱與至少一個類別");
    return;
  }

  try {
    const project = await apiFetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_name: name, task_type: type, class_names: classes }),
    });

    qs("#form-create-project")?.reset();
    appState.newProjectClasses = [];
    renderNewProjectClassList();
    closeCreateProjectModal();

    eventBus.emit("reload-projects", { openProjectId: project.project_id });
    eventBus.emit("toast", "專案已建立");
  } catch (err) {
    eventBus.emit("toast", `建立專案失敗：${err.message}`);
  }
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
  if (!changed) eventBus.emit("toast", "類別已存在");
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
    closeDeleteProjectModal();
    eventBus.emit("project-deleted", projectId);
    eventBus.emit("toast", "專案已刪除");
  } catch (err) {
    if (err.message && err.message.includes("Project not found")) {
      closeDeleteProjectModal();
      eventBus.emit("reload-projects");
      eventBus.emit("toast", "專案已不存在，已重新整理清單");
      return;
    }
    eventBus.emit("toast", `刪除失敗：${err.message}`);
    if (btn) {
      btn.disabled = false;
      btn.classList.remove("btn-disabled");
      btn.innerHTML = `<i class="fa-solid fa-trash"></i> 刪除`;
    }
  }
}

function closeHistoryModal() {
  const modal = qs("#project-history-modal");
  if (modal) modal.hidden = true;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (num) => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
