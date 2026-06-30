import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml } from "../utils.js";

let historySearchQuery = "";
let historyModeFilter = "all";
let inferenceHistoryLoading = false;

export function initProjects() {
  qs("#btn-reload-projects")?.addEventListener("click", () => {
    eventBus.emit("reload-projects");
  });
  qs("#btn-open-create-project")?.addEventListener("click", openCreateProjectModal);
  qs("#btn-close-create-project")?.addEventListener("click", closeCreateProjectModal);
  qs("#btn-cancel-create-project")?.addEventListener("click", closeCreateProjectModal);
  qs("#new-project-type")?.addEventListener("change", syncCreateProjectMode);
  qsa("[data-project-mode]").forEach((button) => {
    button.addEventListener("click", () => setCreateProjectMode(button.dataset.projectMode));
  });
  qs("#project-create-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "project-create-modal") closeCreateProjectModal();
  });

  qs("#btn-add-project-class")?.addEventListener("click", addProjectClassFromInput);
  qs("#new-project-class-input")?.addEventListener("keydown", (event) => {
    if (!["Enter", ",", ";"].includes(event.key)) return;
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

  qs("#project-history-search")?.addEventListener("input", (event) => {
    historySearchQuery = event.target.value || "";
    renderHistoryModal();
  });
  qs("#btn-clear-history-search")?.addEventListener("click", () => {
    historySearchQuery = "";
    const input = qs("#project-history-search");
    if (input) input.value = "";
    renderHistoryModal();
  });
  qsa("[data-history-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      historyModeFilter = btn.dataset.historyFilter || "all";
      renderProjectsPage();
      renderHistoryModal();
    });
  });
  qs("#btn-close-inference-job-detail")?.addEventListener("click", closeInferenceJobDetailModal);
  qs("#inference-job-detail-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "inference-job-detail-modal") closeInferenceJobDetailModal();
  });

  eventBus.on("render-recent-projects-list", (subset) => {
    setHTML("#recent-projects-list", renderProjectList(subset, { includeDelete: false, compact: true }));
    bindProjectListButtons();
  });
  eventBus.on("render-project-history-modal", renderHistoryModal);
  eventBus.on("open-create-project-modal", openCreateProjectModal);

  renderNewProjectClassList();
  syncCreateProjectMode();
}

export function renderProjectsPage() {
  ensureInferenceHistoryLoaded();
  const html = renderProjectList(appState.projects, { includeDelete: true, showFiles: true });
  setHTML("#project-history-list", html);
  const historyProjects = filterProjects(appState.projects || [], "", historyModeFilter);
  const historyJobs = filterInferenceJobs(currentInferenceJobs(), "", historyModeFilter);
  setHTML("#history-list", renderHistoryContent(historyProjects, historyJobs, { includeDelete: true, showFiles: true }));
  syncHistoryFilterControls();
  setText("#history-page-result-count", buildHistoryResultTextWithJobs(historyProjects.length, appState.projects || [], "", historyJobs.length));
  renderHistoryModal();
  bindProjectListButtons();
  bindInferenceJobButtons();
}

export function renderProjectList(projects, options = {}) {
  if (!projects || projects.length === 0) {
    return `<div class="empty-state">目前沒有專案。請使用 New Project 建立新專案。</div>`;
  }

  return projects.map((project) => renderProjectCard(project, options)).join("");
}

function renderHistoryModal() {
  ensureInferenceHistoryLoaded();
  const filtered = filterProjects(appState.projects || [], historySearchQuery, historyModeFilter);
  const filteredJobs = filterInferenceJobs(currentInferenceJobs(), historySearchQuery, historyModeFilter);
  const resultText = buildHistoryResultTextWithJobs(filtered.length, appState.projects || [], historySearchQuery, filteredJobs.length);

  syncHistoryFilterControls();
  setText("#project-history-result-count", resultText);
  setHTML("#modal-project-list", renderHistoryContent(filtered, filteredJobs, { includeDelete: true, showFiles: true }));
  bindProjectListButtons();
  bindInferenceJobButtons();
}

function filterProjects(projects, query, mode = "all") {
  const needle = String(query || "").trim().toLowerCase();

  return projects.filter((project) => {
    if (!matchesHistoryMode(project, mode)) return false;
    if (!needle) return true;

    const files = project.file_summary || {};
    const classes = Array.isArray(project.class_names) ? project.class_names.join(" ") : "";
    const searchable = [
      project.project_name,
      project.project_id,
      project.task_type,
      getProjectHistoryModeLabel(project),
      project.path,
      files.project_root,
      files.layout_mode,
      classes,
    ].filter(Boolean).join(" ").toLowerCase();
    return searchable.includes(needle);
  });
}

function filterInferenceJobs(jobs, query, mode = "all") {
  const needle = String(query || "").trim().toLowerCase();
  return jobs.filter((job) => {
    if (mode !== "all" && job.mode !== mode) return false;
    if (!needle) return true;
    const searchable = [
      job.job_id,
      job.mode,
      job.kind,
      job.backend,
      job.model_id,
      job.run_id,
      job.task_type,
      ...(job.summary?.predicted_labels || []),
      ...(job.summary?.detected_classes || []),
    ].filter(Boolean).join(" ").toLowerCase();
    return searchable.includes(needle);
  });
}

function currentInferenceJobs() {
  if (!appState.currentProjectId || appState.inferenceJobsProjectId !== appState.currentProjectId) return [];
  return appState.inferenceJobs || [];
}

function matchesHistoryMode(project, mode) {
  if (!mode || mode === "all") return true;
  const category = getProjectHistoryCategory(project);
  if (category === "both") return mode === "cnn" || mode === "rnn";
  return category === mode;
}

function getProjectHistoryCategory(project) {
  const taskType = String(project?.task_type || "").toLowerCase();
  const files = project?.file_summary || {};
  const hasRnnSources = Boolean(
    files.sequence_manifest ||
    Number(files.sequence_csv_files || 0) > 0 ||
    Number(files.sequence_files || 0) > 0
  );
  const isRnnTask = ["sequence", "time_series", "timeseries", "rnn"].some((token) => taskType.includes(token));
  const hasCnnSources = Boolean(
    Number(files.images || 0) > 0 ||
    Number(files.labelme_json || 0) > 0 ||
    Number(files.yolo_labels || 0) > 0 ||
    Number(files.best_weights || 0) > 0 ||
    Number(files.last_weights || 0) > 0 ||
    ["detection", "segmentation", "classification", "pose", "obb"].some((token) => taskType.includes(token))
  );

  if ((hasRnnSources || isRnnTask) && hasCnnSources) return "both";
  if (hasRnnSources || isRnnTask) return "rnn";
  return "cnn";
}

function getProjectHistoryModeLabel(project) {
  const category = getProjectHistoryCategory(project);
  if (category === "both") return "CNN/RNN";
  return category.toUpperCase();
}

function buildHistoryResultText(filteredCount, projects, query = historySearchQuery) {
  const total = projects.length;
  const modeLabel = historyModeFilter === "all" ? "全部" : historyModeFilter.toUpperCase();
  const hasSearch = String(query || "").trim();
  if (hasSearch || historyModeFilter !== "all") return `${filteredCount} / ${total} projects · ${modeLabel}`;
  return `${total} projects`;
}

function buildHistoryResultTextWithJobs(filteredCount, projects, query = historySearchQuery, jobCount = 0) {
  const base = buildHistoryResultText(filteredCount, projects, query);
  return jobCount ? `${base}, ${jobCount} jobs` : base;
}

function syncHistoryFilterControls() {
  qsa("[data-history-filter]").forEach((btn) => {
    btn.classList.toggle("active", (btn.dataset.historyFilter || "all") === historyModeFilter);
  });
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
            <span class="badge badge-info">${escapeHtml(getProjectHistoryModeLabel(project))}</span>
            <span class="badge badge-muted">${escapeHtml(project.task_type || "--")}</span>
          </div>
          <p>${escapeHtml(progressText)} · Updated ${escapeHtml(updatedAt || "--")}</p>
        </div>
        <div class="button-row">
          <button class="btn btn-secondary btn-sm" data-open-project="${escapeHtml(project.project_id)}">${escapeHtml(t("historyOpen"))}</button>
          ${options.includeDelete ? `<button class="btn btn-danger btn-sm" data-delete-project="${escapeHtml(project.project_id)}"><i class="fa-solid fa-trash"></i><span>${escapeHtml(t("historyDelete"))}</span></button>` : ""}
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
          ${fileMetric("Sequence manifest", files.sequence_manifest ? "Ready" : "None", files.sequence_manifest ? "success" : "muted")}
          ${fileMetric("Sequence CSV", files.sequence_csv_files ?? 0)}
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

function renderHistoryContent(projects, jobs, options = {}) {
  const projectHtml = renderProjectList(projects, options);
  const jobsHtml = renderInferenceJobList(jobs);
  if (!jobsHtml) return projectHtml;
  return `
    <div class="history-section-block">
      <div class="history-section-title"><span>Inference Jobs</span><small>${escapeHtml(appState.currentProject?.project_name || appState.currentProjectId || "active project")}</small></div>
      ${jobsHtml}
    </div>
    <div class="history-section-block">
      <div class="history-section-title"><span>Projects</span><small>${escapeHtml(projects.length)} item(s)</small></div>
      ${projectHtml}
    </div>
  `;
}

function renderInferenceJobList(jobs) {
  if (inferenceHistoryLoading) {
    return `<div class="empty-state">Loading inference jobs...</div>`;
  }
  if (!appState.currentProjectId) return "";
  if (!jobs || jobs.length === 0) {
    return `<div class="empty-state">No inference jobs for the active project.</div>`;
  }
  return jobs.map(renderInferenceJobCard).join("");
}

function renderInferenceJobCard(job) {
  const isRnn = job.mode === "rnn";
  const summary = job.summary || {};
  const count = isRnn ? job.sequence_count : job.prediction_count;
  const primary = isRnn ? `Sequences: ${count ?? "--"}` : `Predictions: ${count ?? "--"}`;
  const labels = isRnn ? summary.predicted_labels : summary.detected_classes;
  return `
    <article class="project-history-card inference-history-card">
      <div class="project-history-main">
        <div>
          <div class="project-history-title-row">
            <h3>${escapeHtml(job.job_id)}</h3>
            <span class="badge ${isRnn ? "badge-warning" : "badge-info"}">${escapeHtml(String(job.mode || "--").toUpperCase())}</span>
            <span class="badge badge-muted">${escapeHtml(job.kind || "--")}</span>
          </div>
          <p>${escapeHtml(primary)} 繚 ${escapeHtml(formatDate(job.created_at) || "--")}</p>
        </div>
        <div class="button-row">
          <button class="btn btn-secondary btn-sm" data-view-inference-job="${escapeHtml(job.job_id)}">View Result</button>
        </div>
      </div>
      <div class="project-file-summary">
        ${fileMetric("Backend", job.backend || "--")}
        ${fileMetric("Latency", job.inference_time_ms !== undefined ? `${job.inference_time_ms} ms` : "--")}
        ${fileMetric(isRnn ? "Sequences" : "Predictions", count ?? "--")}
        ${fileMetric("Files", job.files?.length ?? 0)}
      </div>
      <div class="project-file-details">
        <div><span>Model</span><code>${escapeHtml(job.model_id || "--")}</code></div>
        <div><span>Run</span><code>${escapeHtml(job.run_id || "--")}</code></div>
        <div><span>Labels</span><code>${escapeHtml(Array.isArray(labels) && labels.length ? labels.join(", ") : "--")}</code></div>
      </div>
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
      closeHistoryModal();
      openDeleteProjectModal(btn.dataset.deleteProject);
    });
  });
}

function bindInferenceJobButtons() {
  qsa("[data-view-inference-job]").forEach((btn) => {
    btn.addEventListener("click", () => openInferenceJobDetail(btn.dataset.viewInferenceJob));
  });
}

async function ensureInferenceHistoryLoaded(force = false) {
  if (!appState.currentProjectId) {
    appState.inferenceJobs = [];
    appState.inferenceJobsProjectId = "";
    return;
  }
  if (!force && appState.inferenceJobsProjectId === appState.currentProjectId) return;
  if (inferenceHistoryLoading) return;

  inferenceHistoryLoading = true;
  appState.inferenceJobsLoading = true;
  try {
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/inference/jobs`);
    appState.inferenceJobs = Array.isArray(payload?.jobs) ? payload.jobs : [];
    appState.inferenceJobsProjectId = appState.currentProjectId;
  } catch (err) {
    appState.inferenceJobs = [];
    appState.inferenceJobsProjectId = appState.currentProjectId;
    eventBus.emit("toast", `Failed to load inference history: ${err.message}`);
  } finally {
    inferenceHistoryLoading = false;
    appState.inferenceJobsLoading = false;
    if (appState.currentPage === "history") renderProjectsPage();
  }
}

async function openInferenceJobDetail(jobId) {
  if (!appState.currentProjectId || !jobId) return;
  setHTML("#inference-job-detail-body", `<div class="empty-state">Loading inference result...</div>`);
  const modal = qs("#inference-job-detail-modal");
  if (modal) modal.hidden = false;
  try {
    const job = await apiFetch(`/api/projects/${appState.currentProjectId}/inference/jobs/${encodeURIComponent(jobId)}`);
    renderInferenceJobDetail(job);
  } catch (err) {
    setHTML("#inference-job-detail-body", `<div class="empty-state">Failed to load inference result: ${escapeHtml(err.message)}</div>`);
  }
}

function closeInferenceJobDetailModal() {
  const modal = qs("#inference-job-detail-modal");
  if (modal) modal.hidden = true;
}

function renderInferenceJobDetail(job) {
  const summary = job.summary || {};
  const predictions = Array.isArray(job.predictions) ? job.predictions : [];
  const rows = predictions.slice(0, 20).map((item) => {
    const confidence = item.confidence !== undefined ? Number(item.confidence).toFixed(4) : "--";
    const label = item.prediction ?? item.class_name ?? "--";
    return `<tr>
      <td><code>${escapeHtml(item.sequence_id || item.class_id || "--")}</code></td>
      <td>${escapeHtml(label)}</td>
      <td>${escapeHtml(confidence)}</td>
      <td>${escapeHtml(item.target ?? "--")}</td>
    </tr>`;
  }).join("");
  const fileLinks = (job.files || []).map((file) =>
    `<a class="btn btn-secondary btn-sm" target="_blank" href="${escapeHtml(file.url)}">${escapeHtml(file.name)}</a>`
  ).join("");
  setHTML("#inference-job-detail-body", `
    <div class="path-list">
      <div class="path-row"><span>Job ID</span><code>${escapeHtml(job.job_id || "--")}</code></div>
      <div class="path-row"><span>Mode</span><code>${escapeHtml(String(job.mode || "--").toUpperCase())}</code></div>
      <div class="path-row"><span>Backend</span><code>${escapeHtml(job.backend || "--")}</code></div>
      <div class="path-row"><span>Model</span><code>${escapeHtml(job.model_id || "--")}</code></div>
      <div class="path-row"><span>Created</span><code>${escapeHtml(formatDate(job.created_at) || "--")}</code></div>
      <div class="path-row"><span>Latency</span><code>${escapeHtml(summary.inference_time_ms ?? "--")} ms</code></div>
    </div>
    <div class="inference-job-file-actions">${fileLinks || "<span class='muted-cell'>No files available.</span>"}</div>
    <div class="data-table compact-table inference-job-prediction-table">
      <table>
        <thead><tr><th>Sequence / Class</th><th>Prediction</th><th>Confidence</th><th>Target</th></tr></thead>
        <tbody>${rows || "<tr><td colspan='4' class='text-center muted-cell'>No prediction rows.</td></tr>"}</tbody>
      </table>
    </div>
  `);
}

function openCreateProjectModal(options = {}) {
  const modal = qs("#project-create-modal");
  if (!modal) return;
  const typeSelect = qs("#new-project-type");
  setCreateProjectMode(options.mode === "rnn" || isSequenceProjectType(options.taskType) ? "rnn" : "cnn", { preserveType: Boolean(options.taskType) });
  if (options.taskType && typeSelect) {
    typeSelect.value = options.taskType;
  }
  if (options.mode === "rnn" && typeSelect && !isSequenceProjectType(typeSelect.value)) {
    typeSelect.value = "sequence_classification";
  }
  syncCreateProjectMode();
  modal.hidden = false;
  qs("#new-project-name")?.focus();
}

function closeCreateProjectModal() {
  const modal = qs("#project-create-modal");
  if (modal) modal.hidden = true;
}

function isSequenceProjectType(taskType) {
  const normalized = String(taskType || "").toLowerCase();
  return normalized.includes("sequence") || normalized.includes("time_series") || normalized.includes("rnn");
}

function getProjectModeFromTaskType(taskType) {
  return isSequenceProjectType(taskType) ? "rnn" : "cnn";
}

function setCreateProjectMode(mode, options = {}) {
  const normalizedMode = mode === "rnn" ? "rnn" : "cnn";
  qsa("[data-project-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.projectMode === normalizedMode);
  });

  const typeSelect = qs("#new-project-type");
  if (!typeSelect) return;

  Array.from(typeSelect.options).forEach((option) => {
    const optionMode = getProjectModeFromTaskType(option.value);
    option.hidden = optionMode !== normalizedMode;
    option.disabled = optionMode !== normalizedMode;
  });

  const selectedMode = getProjectModeFromTaskType(typeSelect.value);
  if (!options.preserveType || selectedMode !== normalizedMode) {
    typeSelect.value = normalizedMode === "rnn" ? "sequence_classification" : "semantic_segmentation";
  }
  syncCreateProjectMode();
}

function syncCreateProjectMode() {
  const type = qs("#new-project-type")?.value || "";
  const isSequence = isSequenceProjectType(type);
  const mode = isSequence ? "rnn" : "cnn";
  qsa("[data-project-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.projectMode === mode);
  });
  setText("#new-project-class-label", isSequence ? "Target labels" : "Class list");
  setText(
    "#new-project-class-hint",
    isSequence
      ? "Optional for RNN projects. CSV feature files must provide label or target columns later."
      : "CNN projects use this list as detection / segmentation classes."
  );
  const input = qs("#new-project-class-input");
  if (input) {
    input.placeholder = isSequence
      ? "Optional labels, e.g. normal, abnormal"
      : "Class name, e.g. class_a; comma separated is supported";
  }
}

async function createProject(event) {
  event.preventDefault();
  const name = qs("#new-project-name")?.value.trim();
  const type = qs("#new-project-type")?.value;
  const classes = [...appState.newProjectClasses];

  if (!name || (!isSequenceProjectType(type) && classes.length === 0)) {
    eventBus.emit("toast", isSequenceProjectType(type) ? "請輸入專案名稱" : "請輸入專案名稱與至少一個類別");
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

    eventBus.emit("reload-projects", {
      openProjectId: project.project_id,
      page: isSequenceProjectType(type) ? "training" : "dashboard"
    });
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
    .split(/[,;]+/)
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
