import { apiFetch, apiUpload } from "../api.js";
import { followServerTask } from "../core/task_progress.js";
import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { buildProjectAssistantContext } from "../core/right_panel.js?v=20260708-rnn-feature-wizard";
import { trainingModeState } from "./training_modes.js?v=20260721-rnn-evaluation-sync";
import { escapeHtml, qs, setHTML, setText } from "../utils.js";

const assistantState = {
  status: null,
  kb: { documents: [], chunks: [] },
  profiles: [],
  retrieval: null,
  lastRun: null,
  agentRuns: [],
  sandbox: null,
  activeSandboxFile: "index.html",
  evaluation: null,
  settings: null,
  conversationState: [],
  drawerOpen: false,
  activeScope: "",
  activeTab: "qa",
};

export function initProjectAssistantImpl() {
  qs("#btn-project-assistant-close")?.addEventListener("click", closeProjectAssistantDrawer);
  qs("#project-assistant-drawer")?.addEventListener("click", (event) => {
    if (event.target.id === "project-assistant-drawer") closeProjectAssistantDrawer();
  });
  qs("#btn-rag-refresh")?.addEventListener("click", () => loadProjectAssistant({ force: true }));
  qs("#btn-rag-ingest")?.addEventListener("click", ingestDocument);
  qs("#btn-rag-upload")?.addEventListener("click", uploadDocumentFile);
  qs("#btn-rag-sync-artifacts")?.addEventListener("click", syncProjectArtifacts);
  qs("#btn-rag-reindex")?.addEventListener("click", reindexKnowledgeBase);
  qs("#btn-rag-clear-kb")?.addEventListener("click", clearKnowledgeBase);
  qs("#btn-rag-query")?.addEventListener("click", runRetrieval);
  qs("#btn-rag-chat")?.addEventListener("click", runProjectAssistantChat);
  qs("#btn-rag-save-file")?.addEventListener("click", saveSandboxFile);
  qs("#btn-rag-export-artifact")?.addEventListener("click", exportSandboxArtifact);
  qs("#btn-rag-eval-report")?.addEventListener("click", generateEvaluationReport);
  qs("#btn-rag-save-settings")?.addEventListener("click", saveAssistantSettings);
  qs(".assistant-tab-list")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-assistant-tab]");
    if (button) activateAssistantTab(button.dataset.assistantTab);
  });
  qs("#rag-sandbox-file")?.addEventListener("change", (event) => {
    assistantState.activeSandboxFile = event.target.value || "index.html";
    renderSandboxEditor();
  });
  qs("#project-assistant-page-context-prompts")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-assistant-prompt]");
    if (!button) return;
    const input = qs("#rag-chat-input");
    if (input) {
      input.value = button.dataset.assistantPrompt || "";
      input.focus();
    }
    assistantState.activeScope = button.dataset.assistantScope || getActiveAssistantScope();
  });
  eventBus.on("open-project-assistant", openProjectAssistantDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && assistantState.drawerOpen) closeProjectAssistantDrawer();
  });
}

export function renderProjectAssistantImplPage() {
  if (!assistantState.drawerOpen) return;
  if (!assistantState.status) {
    loadProjectAssistant();
    return;
  }
  renderStatus();
  renderProjectMode();
  renderPageContext();
  renderKnowledgeBase();
  renderProfiles();
  renderSettings();
  renderRetrievalResults();
  renderChatResult();
  renderAgentRuns();
  renderSandbox();
  renderEvaluation();
  activateAssistantTab(assistantState.activeTab);
}

function activateAssistantTab(tabId) {
  const valid = new Set(["qa", "sources", "settings"]);
  assistantState.activeTab = valid.has(tabId) ? tabId : "qa";
  document.querySelectorAll("[data-assistant-tab]").forEach((button) => {
    const active = button.dataset.assistantTab === assistantState.activeTab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-assistant-tab-panel]").forEach((panel) => {
    const unavailableContext = panel.id === "project-assistant-page-context" && panel.dataset.contextAvailable !== "true";
    panel.hidden = panel.dataset.assistantTabPanel !== assistantState.activeTab || unavailableContext;
  });
}

function renderPageContext() {
  const section = qs("#project-assistant-page-context");
  if (!section) return;
  const status = buildAssistantStatusSnapshot();
  const config = buildProjectAssistantContext(appState.currentPage, status);
  section.dataset.contextAvailable = config ? "true" : "false";
  section.hidden = !config;
  if (!config) {
    assistantState.activeScope = "";
    setText("#project-assistant-page-context-help", "");
    setHTML("#project-assistant-page-context-facts", "");
    setHTML("#project-assistant-page-context-prompts", "");
    return;
  }

  assistantState.activeScope = config.scope || "";
  setText("#project-assistant-page-context-badge", getPageContextBadge(getActiveAssistantPageId()));
  setText("#project-assistant-page-context-help", config.help || "");
  setHTML("#project-assistant-page-context-facts", (config.facts || []).map((fact) => `
    <div class="path-row">
      <span>${escapeHtml(fact.label)}</span>
      <code>${escapeHtml(fact.value)}</code>
    </div>
  `).join("") || `<div class="empty-state">${escapeHtml(t("assistant.noSources"))}</div>`);
  setHTML("#project-assistant-page-context-prompts", (config.prompts || []).map((prompt) => `
    <button type="button" class="assistant-prompt-row" data-assistant-prompt="${escapeHtml(prompt.text)}" data-assistant-scope="${escapeHtml(prompt.scope || config.scope || "")}">
      <span>${escapeHtml(prompt.label)}</span>
      <code>${escapeHtml(prompt.text)}</code>
    </button>
  `).join(""));
}

function getActiveAssistantScope() {
  if (assistantState.activeScope) return assistantState.activeScope;
  const status = buildAssistantStatusSnapshot();
  const config = buildProjectAssistantContext(appState.currentPage, status);
  return config?.scope || "";
}

function buildAssistantStatusSnapshot() {
  const project = appState.currentProject || {};
  const images = Array.isArray(project.images) ? project.images : [];
  const annotatedCount = images.filter((image) => image.annotated || image.annotation_status === "annotated").length;
  return {
    hasProject: Boolean(appState.currentProjectId),
    projectName: project.project_name || project.name || appState.currentProjectId || "",
    taskType: project.task_type || project.task || "",
    architecture: resolveAssistantArchitecture(project),
    hasDataset: images.length > 0 || Boolean(project.dataset_manifest || project.sequence_manifest),
    imageCount: images.length,
    annotatedCount,
    trainReady: Boolean(project.train_ready || project.training_ready),
  };
}

function getPageContextBadge(pageId) {
  const labels = {
    dashboard: t("navDashboard"),
    dataset: t("navDataset"),
    labelme: t("navLabelMe"),
    split: t("navSplit"),
    augmentation: t("navAugmentation"),
    training: t("navTraining"),
    evaluation: t("navEvaluation"),
    inference: t("navInference"),
    "auto-labeling": t("navAutoLabeling"),
    sequence_dataset: t("rnn.training.sequenceCsv"),
    features_labels: t("rnn.training.featureConfig"),
    windowing: t("rnn.training.windowing"),
    sequence_test: t("rnn.training.openSequenceTest"),
    "model-compare": t("compare.title"),
    model_compare: t("compare.title"),
    export: t("navExport"),
    history: t("navHistory"),
    settings: t("navSettings"),
  };
  return labels[pageId] || pageId || "--";
}

function resolveAssistantArchitecture(project = {}) {
  const taskType = String(project.task_type || project.task || "").toLowerCase();
  const explicit = String(project.architecture || project.training_mode || project.training_config?.architecture || "").toLowerCase();
  if (["cnn", "rnn"].includes(explicit)) return explicit;
  return ["sequence", "time_series", "timeseries", "rnn"].some((token) => taskType.includes(token)) ? "rnn" : "cnn";
}

function getActiveAssistantPageId() {
  const architecture = resolveAssistantArchitecture(appState.currentProject || {});
  if (architecture !== "rnn" || appState.currentPage !== "training") return appState.currentPage;
  const panel = String(trainingModeState.activeRnnPanel || "training").replace(/-/g, "_");
  if (panel === "overview") return "dashboard";
  return panel === "model_compare" ? "model-compare" : panel;
}

function getActiveAssistantFilters() {
  const project = appState.currentProject || {};
  const taskType = String(project.task_type || project.task || "").trim().toLowerCase();
  return {
    architecture: resolveAssistantArchitecture(project),
    ...(taskType ? { task_type: taskType } : {}),
  };
}

async function openProjectAssistantDrawer() {
  assistantState.drawerOpen = true;
  const drawer = qs("#project-assistant-drawer");
  if (drawer) {
    drawer.hidden = false;
    drawer.setAttribute("aria-hidden", "false");
  }
  document.body.classList.add("assistant-drawer-open");
  await loadProjectAssistant({ force: !assistantState.status });
  renderProjectAssistantImplPage();
}

function closeProjectAssistantDrawer() {
  assistantState.drawerOpen = false;
  const drawer = qs("#project-assistant-drawer");
  if (drawer) {
    drawer.hidden = true;
    drawer.setAttribute("aria-hidden", "true");
  }
  document.body.classList.remove("assistant-drawer-open");
}

function requireActiveProject() {
  if (appState.currentProjectId) return true;
  eventBus.emit("toast", t("assistant.toast.noActiveProject"));
  return false;
}

async function loadProjectAssistant({ force = false } = {}) {
  if (assistantState.loading && !force) return;
  assistantState.loading = true;
  try {
    const [status, settings, kb, sandbox, runs] = await Promise.all([
      apiFetch(assistantApi("/status")),
      apiFetch(assistantApi("/settings")),
      apiFetch(assistantApi("/knowledge-base")),
      apiFetch(assistantApi("/sandbox")),
      apiFetch(assistantApi("/agent-runs")),
    ]);
    assistantState.status = status;
    assistantState.settings = settings;
    assistantState.kb = kb;
    assistantState.profiles = status.retrieval_profiles || [];
    assistantState.sandbox = sandbox;
    assistantState.agentRuns = runs.runs || [];
    renderProjectAssistantImplPage();
  } finally {
    assistantState.loading = false;
  }
}

async function ingestDocument() {
  if (!requireActiveProject()) return;
  const filename = qs("#rag-doc-filename")?.value?.trim() || "rag-note.md";
  const content = qs("#rag-doc-content")?.value || "";
  if (!content.trim()) {
    eventBus.emit("toast", t("assistant.toast.emptyDocument"));
    return;
  }
  const result = await apiFetch(assistantApi("/knowledge-base/documents"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content }),
  });
  assistantState.status = result.status;
  await loadProjectAssistant({ force: true });
  renderStages(result.document?.ingestion || []);
  eventBus.emit("toast", t("assistant.toast.ingested", { count: result.document?.chunk_count || 0 }));
}

async function uploadDocumentFile() {
  if (!requireActiveProject()) return;
  const input = qs("#rag-upload-file");
  const file = input?.files?.[0];
  if (!file) {
    eventBus.emit("toast", t("assistant.toast.noFile"));
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  const result = await apiUpload(assistantApi("/knowledge-base/upload"), {
    method: "POST",
    body: formData,
  });
  assistantState.status = result.status;
  await loadProjectAssistant({ force: true });
  renderStages(result.document?.ingestion || []);
  eventBus.emit("toast", t("assistant.toast.ingested", { count: result.document?.chunk_count || 0 }));
}

async function syncProjectArtifacts() {
  if (!requireActiveProject()) return;
  const started = await apiFetch(`/api/project-assistant/projects/${encodeURIComponent(appState.currentProjectId)}/sync-artifacts/jobs`, {
    method: "POST",
  });
  const result = await followServerTask(started.job_id, {
    kind: "sync",
    title: t("task.sync.title"),
    button: qs("#btn-rag-sync-artifacts"),
  });
  assistantState.status = result.status;
  await loadProjectAssistant({ force: true });
  eventBus.emit("toast", t("assistant.toast.syncedArtifacts", {
    count: result.document_count || 0,
    chunks: result.chunk_count || 0,
  }));
}

async function reindexKnowledgeBase() {
  if (!requireActiveProject()) return;
  assistantState.status = await apiFetch(assistantApi("/knowledge-base/reindex"), { method: "POST" });
  await loadProjectAssistant({ force: true });
  eventBus.emit("toast", t("assistant.toast.reindexed"));
}

async function clearKnowledgeBase() {
  if (!requireActiveProject()) return;
  const confirmed = window.confirm(t("assistant.confirmClearKb"));
  if (!confirmed) return;
  assistantState.status = await apiFetch(assistantApi("/knowledge-base"), { method: "DELETE" });
  assistantState.retrieval = null;
  assistantState.lastRun = null;
  await loadProjectAssistant({ force: true });
}

async function runRetrieval() {
  if (!requireActiveProject()) return;
  const query = qs("#rag-retrieval-query")?.value || "";
  if (!query.trim()) {
    eventBus.emit("toast", t("assistant.toast.emptyQuery"));
    return;
  }
  assistantState.retrieval = await apiFetch(assistantApi("/retrieval/query"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      profile_id: qs("#rag-retrieval-profile")?.value || "lexical_default",
      scope: getActiveAssistantScope(),
      filters: getActiveAssistantFilters(),
      top_k: 5,
    }),
  });
  renderRetrievalResults();
}

async function runProjectAssistantChat() {
  if (!requireActiveProject()) return;
  const message = qs("#rag-chat-input")?.value || "";
  if (!message.trim()) {
    eventBus.emit("toast", t("assistant.toast.emptyQuestion"));
    return;
  }
  assistantState.lastRun = await apiFetch(assistantApi("/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_state: assistantState.conversationState,
      profile_id: qs("#rag-retrieval-profile")?.value || "lexical_default",
      scope: getActiveAssistantScope(),
      filters: getActiveAssistantFilters(),
    }),
  });
  assistantState.conversationState = assistantState.lastRun.conversation_state || [];
  await loadProjectAssistant({ force: true });
  renderChatResult();
  renderAgentRuns();
}

async function saveSandboxFile() {
  const path = qs("#rag-sandbox-file")?.value || assistantState.activeSandboxFile;
  const content = qs("#rag-sandbox-content")?.value || "";
  assistantState.sandbox = await apiFetch(assistantApi("/sandbox/files"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  renderSandbox();
  eventBus.emit("toast", t("assistant.toast.fileSaved"));
}

async function exportSandboxArtifact() {
  const artifact = await apiFetch(assistantApi("/sandbox/export"), { method: "POST" });
  eventBus.emit("toast", t("assistant.toast.artifactExported", { path: artifact.path || artifact.artifact_id }));
}

async function generateEvaluationReport() {
  assistantState.evaluation = await apiFetch(assistantApi("/evaluation/report"), { method: "POST" });
  renderEvaluation();
  eventBus.emit("toast", t("assistant.toast.reportReady"));
}

async function saveAssistantSettings() {
  const payload = {
    mode: qs("#rag-settings-mode")?.value || "local_search_only",
    local_model_path: qs("#rag-settings-local-model")?.value || "",
    cloud_model: qs("#rag-settings-cloud-model")?.value || "",
    allow_external_requests: Boolean(qs("#rag-settings-external")?.checked),
  };
  assistantState.settings = await apiFetch(assistantApi("/settings"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  await loadProjectAssistant({ force: true });
  eventBus.emit("toast", t("assistant.toast.settingsSaved"));
}

function renderStatus() {
  const status = assistantState.status || {};
  const workspace = status.workspace || {};
  const kb = status.knowledge_base || {};
  setText("#rag-status-project", appState.currentProject?.project_name || appState.currentProject?.name || t("assistant.noActiveProject"));
  const architecture = resolveAssistantArchitecture(appState.currentProject || {}).toUpperCase();
  const pageContext = getPageContextBadge(getActiveAssistantPageId());
  setText("#rag-status-context", appState.currentProjectId ? `${architecture} · ${pageContext}` : pageContext);
  const assistantEnabled = workspace.assistant_enabled ?? workspace.rag_enabled ?? true;
  setText("#rag-status-mode", assistantEnabled ? t("assistant.mode.localSearch") : t("assistant.mode.disabled"));
  setText("#rag-status-documents", kb.document_count ?? 0);
  setText("#rag-kb-badge", t("assistant.docCount", { count: kb.document_count ?? 0 }));
  setText("#rag-agent-count", t("assistant.runCount", { count: assistantState.agentRuns.length }));
}

function renderProjectMode() {
  const project = appState.currentProject || {};
  const hasProject = Boolean(appState.currentProjectId);
  const architecture = resolveAssistantArchitecture(project);
  const mode = !hasProject ? "general" : architecture;
  const icons = { general: "fa-compass", cnn: "fa-images", rnn: "fa-wave-square" };
  const icon = qs("#assistant-project-mode .assistant-project-mode-icon i");
  if (icon) icon.className = `fa-solid ${icons[mode]}`;
  setText("#assistant-project-mode-title", t(`assistant.projectMode.${mode}.title`));
  setText("#assistant-project-mode-help", t(`assistant.projectMode.${mode}.help`));
  setText("#assistant-project-mode-badge", t(`assistant.projectMode.${mode}.badge`));
}

function renderSettings() {
  const settings = assistantState.settings || assistantState.status?.assistant_settings || {};
  const mode = settings.mode || "local_search_only";
  const modeSelect = qs("#rag-settings-mode");
  if (modeSelect && !modeSelect.matches(":focus")) modeSelect.value = mode;
  const localModel = qs("#rag-settings-local-model");
  if (localModel && !localModel.matches(":focus")) localModel.value = settings.local_model_path || "";
  const cloudModel = qs("#rag-settings-cloud-model");
  if (cloudModel && !cloudModel.matches(":focus")) cloudModel.value = settings.cloud_model || "";
  const external = qs("#rag-settings-external");
  if (external) external.checked = Boolean(settings.allow_external_requests);

  const badge = qs("#rag-settings-badge");
  if (badge) {
    badge.textContent = formatAssistantMode(mode);
    badge.className = `summary-badge badge-${mode === "disabled" ? "neutral" : mode === "local_search_only" ? "success" : "warning"}`;
  }
}

function formatAssistantMode(mode) {
  const labels = {
    disabled: t("assistant.settings.mode.disabled"),
    local_search_only: t("assistant.settings.mode.localSearch"),
    local_gguf: t("assistant.settings.mode.localGguf"),
    cloud_api: t("assistant.settings.mode.cloudApi"),
  };
  return labels[mode] || mode || "--";
}

function renderKnowledgeBase() {
  const docs = assistantState.kb?.documents || [];
  const html = docs.length
    ? docs.map((doc) => `
      <article class="assistant-document-card">
        <strong>${escapeHtml(doc.filename)}</strong>
        <span>${escapeHtml(t("assistant.chunkCount", { count: doc.chunk_count || 0 }))}</span>
        <code>${escapeHtml(formatIndexState(doc.index_state))}</code>
      </article>
    `).join("")
    : `<div class="empty-state">${escapeHtml(t("assistant.noDocuments"))}</div>`;
  setHTML("#rag-document-list", html);
}

function formatIndexState(state) {
  const normalized = String(state || "unknown").toLowerCase();
  const labels = {
    empty: t("assistant.indexState.empty"),
    indexed: t("assistant.indexState.indexed"),
    ready: t("assistant.indexState.ready"),
    stale: t("assistant.indexState.stale"),
    unknown: t("assistant.indexState.unknown"),
  };
  return labels[normalized] || state || "--";
}

function renderStages(stages = []) {
  const html = stages.map((stage) => `
    <div class="assistant-stage ${escapeHtml(stage.state)}">
      <strong>${escapeHtml(stage.stage)}</strong>
      <span>${escapeHtml(stage.message || stage.state)}</span>
    </div>
  `).join("");
  setHTML("#rag-ingestion-stages", html);
}

function renderProfiles() {
  const select = qs("#rag-retrieval-profile");
  if (!select) return;
  const current = select.value || "lexical_default";
  select.innerHTML = (assistantState.profiles || []).map((profile) => (
    `<option value="${escapeHtml(profile.profile_id)}">${escapeHtml(profile.name || profile.profile_id)}</option>`
  )).join("");
  select.value = [...select.options].some((option) => option.value === current) ? current : "lexical_default";
}

function renderRetrievalResults() {
  const results = assistantState.retrieval?.results || [];
  setHTML("#rag-retrieval-results", renderSourceList(results, { allowMark: true, query: assistantState.retrieval?.query || "" }));
  bindSourceMarkButtons();
}

function renderChatResult() {
  const run = assistantState.lastRun;
  setHTML("#rag-chat-answer", run?.answer ? escapeHtml(run.answer).replaceAll("\n", "<br>") : escapeHtml(t("assistant.noAnswer")));
  setHTML("#rag-chat-sources", renderSourceList(run?.sources || []));
  setHTML("#rag-agent-trace", renderAgentTrace(run?.agent_trace || []));
}

function renderSourceList(sources = [], { allowMark = false, query = "" } = {}) {
  if (!sources.length) return `<div class="empty-state">${escapeHtml(t("assistant.noSources"))}</div>`;
  return sources.map((source) => `
    <article class="assistant-source-card">
      <div class="assistant-source-head">
        <strong>${escapeHtml(source.source || source.document_id || "--")}</strong>
        <span>${escapeHtml(source.section || "")}</span>
        <code>${escapeHtml(String(source.score ?? "--"))}</code>
      </div>
      <p>${escapeHtml(source.content || "")}</p>
      ${allowMark ? `<button class="btn btn-secondary btn-sm" data-rag-mark-bad="${escapeHtml(source.chunk_id)}" data-rag-query="${escapeHtml(query)}">${escapeHtml(t("assistant.markBad"))}</button>` : ""}
    </article>
  `).join("");
}

function bindSourceMarkButtons() {
  document.querySelectorAll("[data-rag-mark-bad]").forEach((button) => {
    button.addEventListener("click", async () => {
      await apiFetch(assistantApi("/retrieval/marks"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: button.dataset.ragQuery || "",
          chunk_id: button.dataset.ragMarkBad,
          relevance: "bad",
          note: "Marked from Source Search",
        }),
      });
      eventBus.emit("toast", t("assistant.toast.marked"));
    }, { once: true });
  });
}

function assistantApi(path) {
  const params = new URLSearchParams();
  if (appState.currentProjectId) params.set("project_id", appState.currentProjectId);
  if (appState.currentProject?.name) params.set("project_name", appState.currentProject.name);
  const query = params.toString();
  return `/api/project-assistant${path}${query ? `?${query}` : ""}`;
}

function renderAgentTrace(steps = []) {
  if (!steps.length) return `<div class="empty-state">${escapeHtml(t("assistant.noTrace"))}</div>`;
  return steps.map((step) => `
    <div class="assistant-agent-step ${escapeHtml(step.state || "pending")}">
      <strong>${escapeHtml(step.step || "--")}</strong>
      <span>${escapeHtml(step.message || "")}</span>
    </div>
  `).join("");
}

function renderAgentRuns() {
  setHTML("#rag-agent-runs", (assistantState.agentRuns || []).slice(0, 6).map((run) => `
    <article class="assistant-run-card">
      <strong>${escapeHtml(run.run_id)}</strong>
      <span>${escapeHtml(run.query || "")}</span>
      <code>${escapeHtml(t("assistant.sourceCount", { count: run.sources?.length || 0 }))}</code>
    </article>
  `).join("") || `<div class="empty-state">${escapeHtml(t("assistant.noRuns"))}</div>`);
}

function renderSandbox() {
  const sandbox = assistantState.sandbox || {};
  const files = sandbox.files || [];
  const select = qs("#rag-sandbox-file");
  if (select) {
    const current = assistantState.activeSandboxFile || select.value || "index.html";
    select.innerHTML = files.map((file) => `<option value="${escapeHtml(file.path)}">${escapeHtml(file.path)}</option>`).join("");
    select.value = files.some((file) => file.path === current) ? current : files[0]?.path || "index.html";
    assistantState.activeSandboxFile = select.value;
  }
  renderSandboxEditor();
  const iframe = qs("#rag-sandbox-preview");
  if (iframe) iframe.srcdoc = sandbox.preview_html || "";
}

function renderSandboxEditor() {
  const path = assistantState.activeSandboxFile || qs("#rag-sandbox-file")?.value || "index.html";
  const file = (assistantState.sandbox?.files || []).find((item) => item.path === path);
  if (!file) return;
  const textarea = qs("#rag-sandbox-content");
  if (textarea && !textarea.matches(":focus")) textarea.value = file.content || "";
}

function renderEvaluation() {
  const report = assistantState.evaluation;
  if (!report) {
    setHTML("#rag-evaluation-summary", `<div class="empty-state">${escapeHtml(t("assistant.noReport"))}</div>`);
    return;
  }
  setHTML("#rag-evaluation-summary", `
    <div class="assistant-eval-grid">
      <div><span>${escapeHtml(t("assistant.runs"))}</span><strong>${escapeHtml(report.run_count)}</strong></div>
      <div><span>${escapeHtml(t("assistant.citationCoverage"))}</span><strong>${escapeHtml(report.citation_coverage)}</strong></div>
      <div><span>${escapeHtml(t("assistant.sourceHitRate"))}</span><strong>${escapeHtml(report.source_hit_rate)}</strong></div>
      <div><span>${escapeHtml(t("assistant.latency"))}</span><strong>${escapeHtml(report.average_latency_ms)} ms</strong></div>
    </div>
    <div class="path-row"><span>${escapeHtml(t("assistant.reportPath"))}</span><code>${escapeHtml(report.report_path || "--")}</code></div>
  `);
}
