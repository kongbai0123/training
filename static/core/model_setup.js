import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { appState, applyLanguage, applyTheme, t } from "../state.js";
import { escapeHtml, qs } from "../utils.js";

const REVIEW_KEY = "vts-model-setup-reviewed";
const activeJobs = new Map();
let catalogPayload = null;
let loadingPromise = null;
let onboardingStep = 1;
let selectedTask = "all";
let setupMode = "initial";

export function initModelSetup() {
  qs("#btn-open-model-setup")?.addEventListener("click", () => openModelSetup({ mode: "manage" }));
  qs("#btn-close-model-setup")?.addEventListener("click", () => closeModelSetup({ completeInitialSetup: setupMode === "initial", outcome: "skipped" }));
  qs("#btn-skip-model-setup")?.addEventListener("click", () => closeModelSetup({ completeInitialSetup: true, outcome: "skipped" }));
  qs("#btn-complete-model-setup")?.addEventListener("click", () => closeModelSetup({ completeInitialSetup: setupMode === "initial", outcome: "completed" }));
  qs("#btn-install-selected-models")?.addEventListener("click", installSelectedModels);
  qs("#btn-onboarding-next")?.addEventListener("click", () => setOnboardingStep(onboardingStep + 1));
  qs("#btn-onboarding-back")?.addEventListener("click", () => setOnboardingStep(onboardingStep - 1));
  document.querySelectorAll("[data-onboarding-step]").forEach((button) => button.addEventListener("click", () => setOnboardingStep(Number(button.dataset.onboardingStep))));
  document.querySelectorAll("[data-model-task]").forEach((button) => button.addEventListener("click", () => {
    selectedTask = button.dataset.modelTask || "all";
    document.querySelectorAll("[data-model-task]").forEach((item) => item.classList.toggle("active", item === button));
    renderModels(catalogPayload?.models || []);
  }));
  qs("#onboarding-language")?.addEventListener("change", (event) => applyLanguage(event.target.value));
  qs("#onboarding-theme")?.addEventListener("change", (event) => applyTheme(event.target.value));
  qs("#onboarding-density")?.addEventListener("change", applyOnboardingPreferences);
  qs("#onboarding-scale")?.addEventListener("change", applyOnboardingPreferences);
  ["onboarding-offline", "onboarding-autosave", "onboarding-clean-cache"].forEach((id) => qs(`#${id}`)?.addEventListener("change", saveOnboardingPreferences));
  qs("#model-setup-modal")?.addEventListener("click", (event) => {
    if (event.target.id === "model-setup-modal") closeModelSetup({ completeInitialSetup: setupMode === "initial", outcome: "skipped" });
  });
  qs("#model-setup-list")?.addEventListener("click", handleModelAction);
  qs("#model-setup-list")?.addEventListener("change", updateModelSelectionState);
  qs("#model-setup-family-filter")?.addEventListener("change", () => renderModels(catalogPayload?.models || []));
  qs("#btn-select-labelme-component")?.addEventListener("click", () => qs("#labelme-component-file")?.click());
  qs("#labelme-component-file")?.addEventListener("change", installLabelMeComponent);
  eventBus.on("open-model-setup", () => openModelSetup({ mode: "manage" }));
  eventBus.on("language-changed", () => {
    if (catalogPayload) {
      renderModels(catalogPayload.models || []);
      renderSources(catalogPayload.sources || []);
    }
    renderModelSetupSettings();
  });
  restoreOnboardingPreferences();
}

export async function maybeOpenModelSetup() {
  const browserReview = localStorage.getItem(REVIEW_KEY);
  try {
    const state = await apiFetch("/api/onboarding", { suppressToast: true });
    if (state.initial_setup_completed) {
      localStorage.setItem(REVIEW_KEY, state.outcome || "completed");
      return;
    }
    if (browserReview) {
      await persistInitialSetupCompletion("migrated");
      return;
    }
  } catch {
    if (browserReview) return;
  }
  await openModelSetup({ mode: "initial" });
}

export async function openModelSetup({ mode = "manage" } = {}) {
  const modal = qs("#model-setup-modal");
  if (!modal) return;
  setupMode = mode === "initial" ? "initial" : "manage";
  modal.dataset.setupMode = setupMode;
  modal.hidden = false;
  qs("#model-setup-step-nav")?.toggleAttribute("hidden", setupMode !== "initial");
  qs("#btn-skip-model-setup")?.toggleAttribute("hidden", setupMode !== "initial");
  const titleKey = setupMode === "initial" ? "modelSetup.title" : "modelSetup.manageTitle";
  const subtitleKey = setupMode === "initial" ? "modelSetup.subtitle" : "modelSetup.manageSubtitle";
  const title = qs("#model-setup-title");
  const subtitle = qs("#model-setup-subtitle");
  if (title) {
    title.dataset.i18n = titleKey;
    title.textContent = t(titleKey);
  }
  if (subtitle) {
    subtitle.dataset.i18n = subtitleKey;
    subtitle.textContent = t(subtitleKey);
  }
  const completeLabel = qs("#model-setup-complete-label");
  const completeLabelKey = setupMode === "initial" ? "modelSetup.completeWithoutInstall" : "modelSetup.closeManager";
  if (completeLabel) {
    completeLabel.dataset.i18n = completeLabelKey;
    completeLabel.textContent = t(completeLabelKey);
  }
  setOnboardingStep(setupMode === "initial" ? 1 : 4);
  await refreshModelSetup();
}

function setOnboardingStep(step) {
  onboardingStep = Math.max(1, Math.min(4, Number(step) || 1));
  document.querySelectorAll("[data-onboarding-panel]").forEach((panel) => { panel.hidden = Number(panel.dataset.onboardingPanel) !== onboardingStep; });
  document.querySelectorAll("[data-onboarding-step]").forEach((button) => {
    const active = Number(button.dataset.onboardingStep) === onboardingStep;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "step" : "false");
  });
  const back = qs("#btn-onboarding-back");
  const next = qs("#btn-onboarding-next");
  const install = qs("#btn-install-selected-models");
  const complete = qs("#btn-complete-model-setup");
  if (back) back.hidden = setupMode !== "initial" || onboardingStep === 1;
  if (next) next.hidden = onboardingStep === 4;
  if (install) install.hidden = onboardingStep !== 4;
  if (complete) complete.hidden = onboardingStep !== 4;
  saveOnboardingPreferences();
}

function restoreOnboardingPreferences() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("vts-onboarding-preferences") || "{}"); } catch { saved = {}; }
  const values = { "onboarding-language": appState.settings.language, "onboarding-theme": appState.settings.theme, "onboarding-density": saved.density || "comfortable", "onboarding-scale": String(saved.scale || 1) };
  Object.entries(values).forEach(([id, value]) => { const node = qs(`#${id}`); if (node) node.value = value; });
  [["onboarding-offline", saved.offlineFirst !== false], ["onboarding-autosave", saved.autosave !== false], ["onboarding-clean-cache", Boolean(saved.cleanCacheOnStartup)]].forEach(([id, value]) => { const node = qs(`#${id}`); if (node) node.checked = value; });
  applyOnboardingPreferences();
}

function applyOnboardingPreferences() {
  document.body.dataset.density = qs("#onboarding-density")?.value || "comfortable";
  document.documentElement.style.zoom = String(Number(qs("#onboarding-scale")?.value || 1));
  saveOnboardingPreferences();
}

function saveOnboardingPreferences() {
  localStorage.setItem("vts-onboarding-preferences", JSON.stringify({ schemaVersion: 1, density: qs("#onboarding-density")?.value || "comfortable", scale: Number(qs("#onboarding-scale")?.value || 1), offlineFirst: Boolean(qs("#onboarding-offline")?.checked), confirmDownloads: true, autosave: Boolean(qs("#onboarding-autosave")?.checked), cleanCacheOnStartup: Boolean(qs("#onboarding-clean-cache")?.checked) }));
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
    if (selectedTask === "sequence") return model.architecture === "rnn";
    if (model.architecture !== "cnn" || !model.installation_required) return false;
    if (selectedTask !== "all" && model.training_category !== selectedTask) return false;
    if (filter === "all") return true;
    if (filter === "recommended") return model.installed || model.hardware_fit === "recommended";
    return model.model_family === filter;
  });
  const readyTemplates = models.filter((model) => model.architecture === "rnn" && model.usable).length;
  const rnnSummary = qs("#model-setup-rnn-summary");
  if (rnnSummary) rnnSummary.textContent = t("modelSetup.rnnReady", { count: readyTemplates });
  list.innerHTML = installable.map((model) => model.architecture === "rnn" ? renderTemplateCard(model) : renderModelCard(model)).join("") || `<div class="empty-state">${escapeHtml(t("modelSetup.noInstallableModels"))}</div>`;
  updateModelSummary(models);
  updateModelSelectionState();
}

function updateModelSummary(models) {
  const installable = models.filter((model) => model.architecture === "cnn" && model.installation_required);
  const installed = installable.filter((model) => model.installed).length;
  const recommended = installable.filter((model) => !model.installed && (model.recommended || model.hardware_fit === "recommended")).length;
  const values = {
    "model-setup-installed-count": installed,
    "model-setup-available-count": Math.max(0, installable.length - installed),
    "model-setup-recommended-count": recommended,
  };
  Object.entries(values).forEach(([id, value]) => {
    const node = qs(`#${id}`);
    if (node) node.textContent = String(value);
  });
}

function updateModelSelectionState() {
  const selected = [...document.querySelectorAll("[data-model-select]:checked")];
  const installButton = qs("#btn-install-selected-models");
  const summary = qs("#model-setup-selection-summary");
  if (installButton) installButton.disabled = selected.length === 0;
  if (summary) summary.textContent = selected.length
    ? t("modelSetup.selectionCount", { count: selected.length })
    : t("modelSetup.selectionEmpty");
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
  const selected = "";
  const disabled = installed || job?.status === "downloading" ? "disabled" : "";
  const size = formatBytes(model.download_size || 0);
  const taskLabels = {
    image_classification: t("modelSetup.task.imageClassification"),
    object_detection: t("modelSetup.task.objectDetection"),
    instance_segmentation: t("modelSetup.task.instanceSegmentation"),
    semantic_segmentation: t("modelSetup.task.semanticSegmentation"),
  };
  const task = taskLabels[model.training_category] || model.task_family || "--";
  const statusLabel = installed ? t("modelSetup.installed") : t(`modelSetup.fit.${fit}`);
  const statusClass = installed ? "installed" : fit;
  const progress = job ? renderJobProgress(job) : "";
  const scale = resolveModelScale(model);
  return `
    <article class="model-setup-card" data-model-card="${escapeHtml(model.model_id)}">
      <label class="model-setup-select">
        <input type="checkbox" data-model-select value="${escapeHtml(model.model_id)}" ${selected} ${disabled}>
        <span class="model-setup-icon"><i class="fa-solid fa-cube"></i></span>
        <span class="model-setup-copy">
          <strong>${escapeHtml(model.display_name || model.model_id)}</strong>
          <small class="model-scale-help"><b>${escapeHtml(t(`modelSetup.scale.${scale}.name`))}</b><span aria-hidden="true"> &middot; </span>${escapeHtml(t(`modelSetup.scale.${scale}.help`))}</small>
          <span>${escapeHtml(task)} <span aria-hidden="true">&middot;</span> ${escapeHtml(size)}</span>
        </span>
      </label>
      <span class="model-fit-badge ${escapeHtml(statusClass)}">${escapeHtml(statusLabel)}</span>
      ${progress}
    </article>`;
}

function renderTemplateCard(model) {
  return `<article class="model-setup-card model-template-card"><span class="model-setup-icon"><i class="fa-solid fa-wave-square"></i></span><span class="model-setup-copy"><strong>${escapeHtml(model.display_name || model.model_id)}</strong><span>${escapeHtml(t("modelSetup.builtInTemplate"))}</span></span><span class="model-fit-badge ready">${escapeHtml(t("modelSetup.fit.ready"))}</span></article>`;
}

function resolveModelScale(model) {
  const declared = model.decision_profile?.scale;
  if (["nano", "small", "medium", "large", "xlarge"].includes(declared)) return declared;
  const match = String(model.model_id || model.weight || "").match(/(?:^|[-_])(n|s|m|l|x)(?:[-_.]|$)/i);
  return ({ n: "nano", s: "small", m: "medium", l: "large", x: "xlarge" })[match?.[1]?.toLowerCase()] || "medium";
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
  if (setupMode === "initial") await persistInitialSetupCompletion("installed");
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

async function persistInitialSetupCompletion(outcome) {
  localStorage.setItem(REVIEW_KEY, outcome);
  try {
    await apiFetch("/api/onboarding/complete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ outcome }),
      suppressToast: true,
    });
  } catch {
    // Browser storage remains a compatibility fallback; the durable marker is retried next launch.
  }
}

async function closeModelSetup({ completeInitialSetup = false, outcome = "completed" } = {}) {
  if (completeInitialSetup) await persistInitialSetupCompletion(outcome);
  const modal = qs("#model-setup-modal");
  if (modal) modal.hidden = true;
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!value) return "--";
  return value >= 1024 ** 2 ? `${(value / 1024 ** 2).toFixed(1)} MB` : `${Math.round(value / 1024)} KB`;
}
