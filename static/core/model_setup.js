import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { t } from "../state.js";
import { escapeHtml, qs } from "../utils.js";

const REVIEW_KEY = "vts-model-setup-reviewed";
const activeJobs = new Map();
let catalogPayload = null;
let loadingPromise = null;

export function initModelSetup() {
  qs("#btn-open-model-setup")?.addEventListener("click", openModelSetup);
  qs("#btn-close-model-setup")?.addEventListener("click", () => closeModelSetup(true));
  qs("#btn-skip-model-setup")?.addEventListener("click", () => closeModelSetup(true));
  qs("#btn-install-selected-models")?.addEventListener("click", installSelectedModels);
  qs("#model-setup-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "model-setup-modal") closeModelSetup(true);
  });
  qs("#model-setup-list")?.addEventListener("click", handleModelAction);
  qs("#model-setup-family-filter")?.addEventListener("change", () => renderModels(catalogPayload?.models || []));
  qs("#btn-select-labelme-component")?.addEventListener("click", () => qs("#labelme-component-file")?.click());
  qs("#labelme-component-file")?.addEventListener("change", installLabelMeComponent);
  eventBus.on("open-model-setup", openModelSetup);
}

export async function maybeOpenModelSetup() {
  if (localStorage.getItem(REVIEW_KEY)) return;
  await openModelSetup();
}

export async function openModelSetup() {
  const modal = qs("#model-setup-modal");
  if (!modal) return;
  modal.hidden = false;
  await refreshModelSetup();
}

export async function renderModelSetupSettings() {
  const target = qs("#settings-model-setup-summary");
  if (!target) return;
  try {
    const payload = await loadCatalog();
    const installable = payload.models.filter((model) => model.installation_required);
    const installed = installable.filter((model) => model.installed).length;
    target.textContent = t("modelSetup.settingsSummary", { installed, total: installable.length });
  } catch {
    target.textContent = t("modelSetup.statusUnavailable");
  }
}

async function refreshModelSetup({ force = false } = {}) {
  const list = qs("#model-setup-list");
  if (list) list.innerHTML = `<div class="empty-state">${escapeHtml(t("common.loading"))}</div>`;
  try {
    catalogPayload = await loadCatalog(force);
    renderHardware(catalogPayload.hardware || {});
    renderModels(catalogPayload.models || []);
    renderSources(catalogPayload.sources || []);
    await refreshLabelMeComponent();
    await renderModelSetupSettings();
  } catch (error) {
    if (list) list.innerHTML = `<div class="empty-state">${escapeHtml(t("modelSetup.loadFailed", { message: error.message }))}</div>`;
  }
}

async function refreshLabelMeComponent() {
  const statusNode = qs("#labelme-component-status");
  const detailNode = qs("#labelme-component-detail");
  const button = qs("#btn-select-labelme-component");
  try {
    const status = await apiFetch("/api/components/labelme", { suppressToast: true });
    if (statusNode) statusNode.textContent = t(`modelSetup.labelme.status.${status.status}`);
    if (detailNode) detailNode.textContent = status.offline_ready
      ? t("modelSetup.labelme.offlineReady", { version: status.version || "--" })
      : t("modelSetup.labelme.optionalHelp");
    if (button) button.textContent = status.offline_ready ? t("modelSetup.labelme.replace") : t("modelSetup.labelme.install");
  } catch (error) {
    if (statusNode) statusNode.textContent = t("modelSetup.statusUnavailable");
    if (detailNode) detailNode.textContent = error.message;
  }
}

async function installLabelMeComponent(event) {
  const input = event.currentTarget;
  const file = input.files?.[0];
  if (!file) return;
  const confirmed = window.confirm(t("modelSetup.labelme.confirm", { file: file.name }));
  if (!confirmed) {
    input.value = "";
    return;
  }
  const button = qs("#btn-select-labelme-component");
  if (button) button.disabled = true;
  try {
    const form = new FormData();
    form.append("confirm", "true");
    form.append("file", file);
    const status = await apiFetch("/api/components/labelme/install", { method: "POST", body: form });
    eventBus.emit("toast", t("modelSetup.labelme.installed", { version: status.version || "--" }));
    await refreshLabelMeComponent();
  } catch (error) {
    eventBus.emit("toast", t("modelSetup.labelme.installFailed", { message: error.message }));
  } finally {
    if (button) button.disabled = false;
    input.value = "";
  }
}

function loadCatalog(force = false) {
  if (catalogPayload && !force) return Promise.resolve(catalogPayload);
  if (!loadingPromise || force) {
    loadingPromise = apiFetch("/api/models/catalog?usage=all", { suppressToast: true })
      .then((payload) => {
        catalogPayload = payload;
        return payload;
      })
      .finally(() => { loadingPromise = null; });
  }
  return loadingPromise;
}

function renderHardware(hardware) {
  const gpu = hardware.gpu || {};
  const gpuDevice = (gpu.devices || [])[0] || {};
  const values = {
    "model-setup-gpu": gpuDevice.name || t("modelSetup.cpuOnly"),
    "model-setup-vram": gpuDevice.vram_total_mb ? `${Math.round(gpuDevice.vram_total_mb / 1024)} GB` : "--",
    "model-setup-memory": hardware.memory?.total_gb ? `${hardware.memory.total_gb} GB` : "--",
    "model-setup-disk": hardware.disk?.available_gb ? `${hardware.disk.available_gb} GB` : "--",
  };
  Object.entries(values).forEach(([id, value]) => {
    const node = qs(`#${id}`);
    if (node) node.textContent = value;
  });
}

function renderModels(models) {
  const list = qs("#model-setup-list");
  if (!list) return;
  const filter = qs("#model-setup-family-filter")?.value || "recommended";
  const installable = models.filter((model) => {
    if (model.architecture !== "cnn" || !model.installation_required) return false;
    if (filter === "all") return true;
    if (filter === "recommended") return model.installed || model.hardware_fit === "recommended";
    return model.model_family === filter;
  });
  const readyTemplates = models.filter((model) => model.architecture === "rnn" && model.usable).length;
  const rnnSummary = qs("#model-setup-rnn-summary");
  if (rnnSummary) rnnSummary.textContent = t("modelSetup.rnnReady", { count: readyTemplates });
  list.innerHTML = installable.map(renderModelCard).join("") || `<div class="empty-state">${escapeHtml(t("modelSetup.noInstallableModels"))}</div>`;
}

function renderSources(sources) {
  const target = qs("#model-setup-sources");
  if (!target) return;
  target.innerHTML = sources.map((source) => `
    <div class="model-source-row">
      <span class="model-source-icon"><i class="fa-solid ${source.network_required ? "fa-cloud-arrow-down" : "fa-folder-open"}"></i></span>
      <span><strong>${escapeHtml(t(`modelSetup.source.${source.source_id}`))}</strong><small>${escapeHtml(t(`modelSetup.availability.${source.availability}`))}</small></span>
    </div>`).join("");
}

function renderModelCard(model) {
  const job = [...activeJobs.values()].find((item) => item.model_id === model.model_id);
  const installed = Boolean(model.installed);
  const fit = model.hardware_fit || "compatible";
  const recommended = fit === "recommended" || Boolean(model.recommended);
  const selected = !installed && recommended ? "checked" : "";
  const disabled = installed || job?.status === "downloading" || fit === "incompatible" ? "disabled" : "";
  const size = formatBytes(model.download_size || 0);
  const task = model.task_family === "segmentation" ? t("modelSetup.segmentation") : t("modelSetup.detection");
  const statusLabel = installed ? t("modelSetup.installed") : t(`modelSetup.fit.${fit}`);
  const statusClass = installed ? "installed" : fit;
  const progress = job ? renderJobProgress(job) : "";
  return `
    <article class="model-setup-card" data-model-card="${escapeHtml(model.model_id)}">
      <label class="model-setup-select">
        <input type="checkbox" data-model-select value="${escapeHtml(model.model_id)}" ${selected} ${disabled}>
        <span class="model-setup-icon"><i class="fa-solid fa-cube"></i></span>
        <span class="model-setup-copy">
          <strong>${escapeHtml(model.display_name || model.model_id)}</strong>
          <span>${escapeHtml(task)} · ${escapeHtml(size)}</span>
        </span>
      </label>
      <span class="model-fit-badge ${escapeHtml(statusClass)}">${escapeHtml(statusLabel)}</span>
      ${progress}
    </article>`;
}

function renderJobProgress(job) {
  const progress = Number(job.progress || 0);
  const status = t(`modelSetup.job.${job.status}`);
  const action = job.status === "downloading"
    ? `<button type="button" class="btn btn-secondary btn-sm" data-model-cancel="${escapeHtml(job.job_id)}">${escapeHtml(t("common.cancel"))}</button>`
    : ["failed", "cancelled"].includes(job.status)
      ? `<button type="button" class="btn btn-secondary btn-sm" data-model-retry="${escapeHtml(job.job_id)}">${escapeHtml(t("common.retry"))}</button>`
      : "";
  return `
    <div class="model-install-progress">
      <div class="progress-track"><div class="progress-fill" style="width:${Math.max(0, Math.min(100, progress))}%"></div></div>
      <span>${escapeHtml(status)} ${progress ? `${progress.toFixed(0)}%` : ""}</span>
      ${action}
    </div>`;
}

async function installSelectedModels() {
  const selected = [...document.querySelectorAll("[data-model-select]:checked")].map((input) => input.value);
  if (!selected.length) {
    eventBus.emit("toast", t("modelSetup.selectAtLeastOne"));
    return;
  }
  localStorage.setItem(REVIEW_KEY, "installed");
  for (const modelId of selected) {
    try {
      const job = await apiFetch("/api/models/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model_id: modelId, confirm: true }),
      });
      activeJobs.set(job.job_id, job);
      renderModels(catalogPayload?.models || []);
      pollInstallJob(job.job_id);
    } catch (error) {
      eventBus.emit("toast", t("modelSetup.installFailed", { message: error.message }));
    }
  }
}

async function pollInstallJob(jobId) {
  try {
    const job = await apiFetch(`/api/models/install/jobs/${encodeURIComponent(jobId)}`, { suppressToast: true });
    activeJobs.set(jobId, job);
    renderModels(catalogPayload?.models || []);
    if (["queued", "downloading"].includes(job.status)) {
      window.setTimeout(() => pollInstallJob(jobId), 500);
      return;
    }
    if (job.status === "completed") {
      eventBus.emit("toast", t("modelSetup.installCompleted", { model: job.display_name }));
      await refreshModelSetup({ force: true });
    } else if (job.status === "failed") {
      eventBus.emit("toast", t("modelSetup.installFailed", { message: job.error || job.status }));
    }
  } catch (error) {
    eventBus.emit("toast", t("modelSetup.installFailed", { message: error.message }));
  }
}

async function handleModelAction(event) {
  const cancel = event.target.closest("[data-model-cancel]");
  const retry = event.target.closest("[data-model-retry]");
  try {
    if (cancel) {
      const job = await apiFetch(`/api/models/install/jobs/${encodeURIComponent(cancel.dataset.modelCancel)}/cancel`, { method: "POST" });
      activeJobs.set(job.job_id, job);
      renderModels(catalogPayload?.models || []);
    } else if (retry) {
      const job = await apiFetch(`/api/models/install/jobs/${encodeURIComponent(retry.dataset.modelRetry)}/retry`, { method: "POST" });
      activeJobs.set(job.job_id, job);
      renderModels(catalogPayload?.models || []);
      pollInstallJob(job.job_id);
    }
  } catch (error) {
    eventBus.emit("toast", t("modelSetup.installFailed", { message: error.message }));
  }
}

function closeModelSetup(reviewed) {
  if (reviewed) localStorage.setItem(REVIEW_KEY, "skipped");
  const modal = qs("#model-setup-modal");
  if (modal) modal.hidden = true;
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!value) return "--";
  return value >= 1024 ** 2 ? `${(value / 1024 ** 2).toFixed(1)} MB` : `${Math.round(value / 1024)} KB`;
}
