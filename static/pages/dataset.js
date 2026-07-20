import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { apiFetch, apiUpload } from "../api.js";
import { beginTask, followServerTask } from "../core/task_progress.js";
import { qs, setText, setHTML, escapeHtml, collectDroppedFiles } from "../utils.js";

const IMAGE_RE = /\.(jpg|jpeg|png|bmp)$/i;
const VIDEO_RE = /\.(mp4|avi|mkv|mov|wmv|flv|webm)$/i;
const ANNO_RE = /\.(json|txt)$/i;

export function initDataset() {
  qs("#btn-dataset-add-class")?.addEventListener("click", addDatasetClass);
  qs("#input-dataset-new-class")?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addDatasetClass();
  });

  qs("#dataset-classes-list-box")?.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-remove-dataset-class]");
    if (!btn) return;
    const name = btn.dataset.removeDatasetClass;
    appState.currentProjectClasses = (appState.currentProjectClasses || []).filter((c) => c !== name);
    renderDatasetClassesEditList();
  });

  qs("#btn-save-dataset-classes")?.addEventListener("click", saveDatasetClasses);
  qs("#btn-import-local")?.addEventListener("click", importLocalImages);
  qs("#btn-import-video")?.addEventListener("click", importLocalVideo);
  qs("#btn-trigger-quality")?.addEventListener("click", runQualityCheck);
  qs("#btn-copy-zip-path")?.addEventListener("click", copyZipPath);

  setupVideoDropZone();
  setupDatasetDropZone();

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

  eventBus.on("language-changed", () => renderDatasetPage(getProjectStatus(appState.currentProject)));
}

function addDatasetClass() {
  const input = qs("#input-dataset-new-class");
  const names = parseClassTokens(input?.value);
  if (!names.length) return;
  appState.currentProjectClasses ||= [];
  let changed = false;
  names.forEach((name) => {
    const exists = appState.currentProjectClasses.some((item) => item.toLowerCase() === name.toLowerCase());
    if (exists) return;
    appState.currentProjectClasses.push(name);
    changed = true;
  });
  if (!changed) eventBus.emit("toast", t("dataset.toast.duplicateClass"));
  if (input) input.value = "";
  renderDatasetClassesEditList();
}

function parseClassTokens(rawValue) {
  return String(rawValue || "")
    .split(/[,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

async function saveDatasetClasses() {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", t("dataset.toast.noProject"));
    return;
  }
  const btn = qs("#btn-save-dataset-classes");
  if (btn) btn.disabled = true;
  try {
    await apiFetch(`/api/projects/${appState.currentProjectId}/classes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_names: appState.currentProjectClasses || [] })
    });
    eventBus.emit("toast", t("dataset.toast.classesSaved"));
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", t("dataset.toast.classesFailed", { message: err.message }));
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function importLocalImages() {
  const path = qs("#input-local-folder")?.value.trim();
  if (!path) return eventBus.emit("toast", t("dataset.toast.localPathRequired"));
  const formData = new FormData();
  formData.append("path", path);
  const task = beginTask({ kind: "import", title: t("task.import.title"), stage: t("task.import.processing"), method: "POST" });
  try {
    const launch = await apiFetch(`/api/projects/${appState.currentProjectId}/import-local/jobs`, { method: "POST", body: formData, suppressProgress: true });
    const data = await followServerTask(launch.job_id, { controller: task, kind: "import", title: t("task.import.title") });
    eventBus.emit("toast", data.message || t("dataset.toast.localImportDone"));
    eventBus.emit("refresh-project");
  } catch (err) {
    task.fail({ message: err.message });
    eventBus.emit("toast", t("dataset.toast.localImportFailed", { message: err.message }));
  }
}

async function importLocalVideo() {
  const videoPath = qs("#input-video-path")?.value.trim();
  const fps = qs("#input-video-fps")?.value || "1";
  if (!videoPath) return eventBus.emit("toast", t("dataset.toast.videoPathRequired"));
  const formData = new FormData();
  formData.append("video_path", videoPath);
  formData.append("fps", fps);
  const task = beginTask({ kind: "import", title: t("task.import.title"), stage: t("task.import.processing"), method: "POST" });
  try {
    const launch = await apiFetch(`/api/projects/${appState.currentProjectId}/import-video/jobs`, { method: "POST", body: formData, suppressProgress: true });
    const data = await followServerTask(launch.job_id, { controller: task, kind: "import", title: t("task.import.title") });
    eventBus.emit("toast", data.message || t("dataset.toast.videoDone"));
    eventBus.emit("refresh-project");
  } catch (err) {
    task.fail({ message: err.message });
    eventBus.emit("toast", t("dataset.toast.videoFailed", { message: err.message }));
  }
}

function setupVideoDropZone() {
  const dropZone = qs("#video-drop-zone");
  const input = qs("#input-video-file");
  if (!dropZone || !input) return;
  input.style.display = "none";
  input.multiple = true;
  input.accept = "video/*";
  dropZone.addEventListener("click", () => input.click());
  input.addEventListener("change", async (event) => {
    await uploadVideoFiles([...(event.target.files || [])]);
    input.value = "";
  });
  setupDropEvents(dropZone, async (event) => uploadVideoFiles(await collectDroppedFiles(event.dataTransfer)));
}

function setupDatasetDropZone() {
  const dropZone = qs("#zip-drop-zone");
  const input = qs("#input-zip-file");
  if (!dropZone || !input) return;
  input.style.display = "none";
  input.multiple = true;
  input.setAttribute("webkitdirectory", "");
  input.setAttribute("directory", "");
  dropZone.addEventListener("click", () => input.click());
  input.addEventListener("change", async (event) => {
    await uploadDatasetFiles([...(event.target.files || [])]);
    input.value = "";
  });
  setupDropEvents(dropZone, async (event) => uploadDatasetFiles(await collectDroppedFiles(event.dataTransfer)));
}

function setupDropEvents(dropZone, onDrop) {
  ["dragenter", "dragover"].forEach((name) => {
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.add("dz-drag-hover");
    }, true);
  });
  ["dragleave", "drop"].forEach((name) => {
    dropZone.addEventListener(name, (event) => {
      event.preventDefault();
      event.stopPropagation();
      dropZone.classList.remove("dz-drag-hover");
    }, true);
  });
  dropZone.addEventListener("drop", onDrop, true);
}

async function uploadVideoFiles(files) {
  if (!appState.currentProjectId) return eventBus.emit("toast", t("dataset.toast.uploadProjectFirst"));
  const allFiles = [...files];
  const videoFiles = allFiles.filter((file) => VIDEO_RE.test(file.name));
  const otherFiles = allFiles.filter((file) => !VIDEO_RE.test(file.name));
  if (otherFiles.length) eventBus.emit("toast", t("dataset.toast.videoFiltered", { count: otherFiles.length }));
  if (!videoFiles.length) return eventBus.emit("toast", t("dataset.toast.videoNone"));
  if (videoFiles.length > 5) return eventBus.emit("toast", t("dataset.toast.videoTooMany"));

  const dropZone = qs("#video-drop-zone");
  const progress = beginTask({
    jobId: `video-import-${Date.now()}`,
    kind: "import",
    title: t("dataset.progress.videoProcessing"),
    stage: t("dataset.progress.analyzing"),
    method: "POST",
    inlineHost: dropZone?.parentElement,
  });
  const fps = qs("#input-video-fps")?.value || "1";
  try {
    for (let idx = 0; idx < videoFiles.length; idx += 1) {
      const file = videoFiles[idx];
      progress.update({ percent: Math.round((idx / videoFiles.length) * 100), indeterminate: false, message: t("dataset.progress.videoUploading", { name: file.name, index: idx + 1, total: videoFiles.length }) });
      const formData = new FormData();
      formData.append("file", file);
      formData.append("fps", fps);
      const launch = await apiUpload(`/api/projects/${appState.currentProjectId}/upload-video/jobs`, { method: "POST", body: formData });
      await followServerTask(launch.job_id, { kind: "import", title: t("task.import.title") });
    }
    progress.complete({ message: t("dataset.toast.videoDone") });
    eventBus.emit("refresh-project");
  } catch (err) {
    progress.fail({ message: err.message });
    eventBus.emit("toast", t("dataset.toast.videoFailed", { message: err.message }));
  }
}

async function uploadDatasetFiles(files) {
  if (!appState.currentProjectId) return eventBus.emit("toast", t("dataset.toast.uploadProjectFirst"));
  const allFiles = [...files];
  if (!allFiles.length) return eventBus.emit("toast", t("dataset.toast.noFiles"));

  const dropZone = qs("#zip-drop-zone");

  const zipFiles = allFiles.filter((file) => file.name.toLowerCase().endsWith(".zip"));
  const imageFiles = allFiles.filter((file) => IMAGE_RE.test(file.name));
  const videoFiles = allFiles.filter((file) => VIDEO_RE.test(file.name));
  const annoFiles = allFiles.filter((file) => ANNO_RE.test(file.name));

  if (videoFiles.length && annoFiles.length) eventBus.emit("toast", t("dataset.toast.filteredMixed", { videos: videoFiles.length, annotations: annoFiles.length }));
  else if (videoFiles.length) eventBus.emit("toast", t("dataset.toast.filteredVideos", { count: videoFiles.length }));
  else if (annoFiles.length) eventBus.emit("toast", t("dataset.toast.filteredAnnotations", { count: annoFiles.length }));

  if (!zipFiles.length && !imageFiles.length) {
    return eventBus.emit("toast", t("dataset.toast.noImageOrZip"));
  }
  const progress = beginTask({
    jobId: `dataset-import-${Date.now()}`,
    kind: "import",
    title: t("task.import.title"),
    stage: t("dataset.progress.analyzing"),
    method: "POST",
    inlineHost: dropZone?.parentElement,
  });
  let importedImages = 0;
  let duplicateSameHash = 0;
  let renamedCount = 0;
  try {
    for (let idx = 0; idx < zipFiles.length; idx += 1) {
      const file = zipFiles[idx];
      progress.update({ percent: Math.round((idx / Math.max(1, zipFiles.length)) * 100), indeterminate: false, message: t("dataset.progress.processingZip", { name: file.name }) });
      const formData = new FormData();
      formData.append("file", file, file.name);
      const launch = await apiUpload(`/api/projects/${appState.currentProjectId}/import-zip/jobs`, { method: "POST", body: formData });
      const data = await followServerTask(launch.job_id, { kind: "import", title: t("task.import.title") });
      importedImages += data.imported_images || 0;
    }

    const batchSize = 50;
    const totalBatches = Math.ceil(imageFiles.length / batchSize);
    for (let i = 0; i < imageFiles.length; i += batchSize) {
      const batchIndex = Math.floor(i / batchSize) + 1;
      const batch = imageFiles.slice(i, i + batchSize);
      progress.update({ percent: Math.round((i / Math.max(1, imageFiles.length)) * 100), indeterminate: false, message: t("dataset.progress.uploadingBatch", { index: batchIndex, total: totalBatches, count: batch.length }) });
      const formData = new FormData();
      batch.forEach((file) => formData.append("files", file, file.name));
      const data = await apiUpload(`/api/projects/${appState.currentProjectId}/upload-images`, { method: "POST", body: formData });
      importedImages += data.uploaded_count || 0;
      duplicateSameHash += data.duplicate_same_hash || 0;
      renamedCount += data.renamed_same_name_diff_hash || 0;
    }

    progress.update({ percent: 95, indeterminate: false, message: t("dataset.progress.syncingDetail") });
    try {
      const syncTask = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/sync/jobs`, { method: "POST" });
      await followServerTask(syncTask.job_id, { kind: "sync", title: t("task.sync.title") });
    } catch (err) { console.warn("Auto sync failed", err); }
    progress.complete({ message: t("dataset.progress.importSummary", { imported: importedImages, duplicates: duplicateSameHash, renamed: renamedCount }) });
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", t("dataset.toast.importFailed", { message: err.message }));
    progress.fail({ message: err.message });
  }
}

async function runQualityCheck() {
  try {
    const started = await apiFetch(`/api/projects/${appState.currentProjectId}/quality-check/jobs`, { method: "POST" });
    const report = await followServerTask(started.job_id, {
      kind: "evaluation",
      title: t("task.evaluation.title"),
      button: qs("#btn-trigger-quality"),
    });
    eventBus.emit("toast", t("dataset.toast.qualityDone", { score: report.score }));
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", t("dataset.toast.qualityFailed", { message: err.message }));
  }
}

function copyZipPath() {
  const text = qs("#dataset-zip-storage-path")?.textContent;
  if (!text || text === "Not loaded" || text === t("common.notLoaded")) return;
  navigator.clipboard.writeText(text).then(() => eventBus.emit("toast", t("dataset.toast.pathCopied")));
}

export function renderDatasetPage(status) {
  const project = appState.currentProject;
  const rawImages = (project?.images || []).filter((img) => !img.is_augmented);
  const zipPath = status.datasetPath ? `${status.datasetPath}/packages/zip` : t("common.notLoaded");
  setText("#dataset-zip-storage-path", zipPath);

  if (!appState.currentProjectClasses && project) appState.currentProjectClasses = [...(project.class_names || [])];
  renderDatasetClassesEditList();

  const query = qs("#search-image")?.value?.toLowerCase() || "";
  const filter = qs("#filter-status")?.value || "all";
  const filtered = rawImages.filter((img) => img.filename.toLowerCase().includes(query) && (filter === "all" || img.status === filter));
  setText("#dataset-count-total", filtered.length);
  setText("#health-score-val", project?.dataset_health?.score ?? "--");

  if (!status.hasProject) return setHTML("#dataset-thumbnails", `<div class="empty-state">${escapeHtml(t("dataset.emptyNoProject"))}</div>`);
  if (!filtered.length) return setHTML("#dataset-thumbnails", `<div class="empty-state">${escapeHtml(t("dataset.emptyNoImages"))}</div>`);

  const visibleImages = filtered.slice(0, appState.datasetVisibleLimit);
  const hiddenCount = Math.max(0, filtered.length - visibleImages.length);
  const cards = visibleImages.map((img) => `
    <article class="thumb-card">
      <div class="thumb-image-frame"><img src="/api/projects/${encodeURIComponent(appState.currentProjectId)}/thumbnails/${encodeURIComponent(img.filename)}" loading="lazy" decoding="async" fetchpriority="low" alt="${escapeHtml(img.filename)}"></div>
      <footer><strong title="${escapeHtml(img.filename)}">${escapeHtml(img.filename)}</strong><span class="badge ${badgeClassForStatus(img.status)}">${escapeHtml(img.status || "unknown")}</span></footer>
    </article>
  `);
  if (hiddenCount > 0) {
    cards.push(`<button type="button" class="load-more-card" id="btn-load-more-images"><strong>${escapeHtml(t("dataset.loadMore"))}</strong><span>${escapeHtml(t("dataset.shownCount", { shown: visibleImages.length, total: filtered.length }))}</span></button>`);
  }
  setHTML("#dataset-thumbnails", cards.join(""));
}

function renderDatasetClassesEditList() {
  const box = qs("#dataset-classes-list-box");
  if (!box) return;
  const classes = appState.currentProjectClasses || [];
  if (!classes.length) {
    box.innerHTML = `<span class="empty-class-list">${escapeHtml(t("dataset.emptyNoClasses"))}</span>`;
    return;
  }
  box.innerHTML = classes.map((cls) => `<span class="class-chip">${escapeHtml(cls)}<button type="button" data-remove-dataset-class="${escapeHtml(cls)}" style="border:none;background:none;cursor:pointer;color:var(--text-muted);">&times;</button></span>`).join("");
}

function badgeClassForStatus(status) {
  if (status === "annotated") return "badge-success";
  if (status === "flagged") return "badge-warning";
  if (status === "skipped") return "badge-danger";
  return "badge-muted";
}
