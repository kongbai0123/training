import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
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
};

export function initProjectAssistantImpl() {
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
  qs("#rag-sandbox-file")?.addEventListener("change", (event) => {
    assistantState.activeSandboxFile = event.target.value || "index.html";
    renderSandboxEditor();
  });
}

export function renderProjectAssistantImplPage() {
  if (appState.currentPage !== "project-assistant") return;
  if (!assistantState.status) {
    loadProjectAssistant();
    return;
  }
  renderStatus();
  renderKnowledgeBase();
  renderProfiles();
  renderSettings();
  renderRetrievalResults();
  renderChatResult();
  renderAgentRuns();
  renderSandbox();
  renderEvaluation();
}

function requireActiveProject() {
  if (appState.currentProjectId) return true;
  eventBus.emit("toast", t("rag.toast.noActiveProject"));
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
    eventBus.emit("toast", t("rag.toast.emptyDocument"));
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
  eventBus.emit("toast", t("rag.toast.ingested", { count: result.document?.chunk_count || 0 }));
}

async function uploadDocumentFile() {
  if (!requireActiveProject()) return;
  const input = qs("#rag-upload-file");
  const file = input?.files?.[0];
  if (!file) {
    eventBus.emit("toast", t("rag.toast.noFile"));
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  const result = await apiFetch(assistantApi("/knowledge-base/upload"), {
    method: "POST",
    body: formData,
  });
  assistantState.status = result.status;
  await loadProjectAssistant({ force: true });
  renderStages(result.document?.ingestion || []);
  eventBus.emit("toast", t("rag.toast.ingested", { count: result.document?.chunk_count || 0 }));
}

async function syncProjectArtifacts() {
  if (!requireActiveProject()) return;
  const result = await apiFetch(`/api/project-assistant/projects/${encodeURIComponent(appState.currentProjectId)}/sync-artifacts`, {
    method: "POST",
  });
  assistantState.status = result.status;
  await loadProjectAssistant({ force: true });
  eventBus.emit("toast", t("rag.toast.syncedArtifacts", {
    count: result.document_count || 0,
    chunks: result.chunk_count || 0,
  }));
}

async function reindexKnowledgeBase() {
  if (!requireActiveProject()) return;
  assistantState.status = await apiFetch(assistantApi("/knowledge-base/reindex"), { method: "POST" });
  await loadProjectAssistant({ force: true });
  eventBus.emit("toast", t("rag.toast.reindexed"));
}

async function clearKnowledgeBase() {
  if (!requireActiveProject()) return;
  const confirmed = window.confirm(t("rag.confirmClearKb"));
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
    eventBus.emit("toast", t("rag.toast.emptyQuery"));
    return;
  }
  assistantState.retrieval = await apiFetch(assistantApi("/retrieval/query"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      profile_id: qs("#rag-retrieval-profile")?.value || "lexical_default",
      top_k: 5,
    }),
  });
  renderRetrievalResults();
}

async function runProjectAssistantChat() {
  if (!requireActiveProject()) return;
  const message = qs("#rag-chat-input")?.value || "";
  if (!message.trim()) {
    eventBus.emit("toast", t("rag.toast.emptyQuestion"));
    return;
  }
  assistantState.lastRun = await apiFetch(assistantApi("/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_state: assistantState.conversationState,
      profile_id: qs("#rag-retrieval-profile")?.value || "lexical_default",
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
  eventBus.emit("toast", t("rag.toast.fileSaved"));
}

async function exportSandboxArtifact() {
  const artifact = await apiFetch(assistantApi("/sandbox/export"), { method: "POST" });
  eventBus.emit("toast", t("rag.toast.artifactExported", { path: artifact.path || artifact.artifact_id }));
}

async function generateEvaluationReport() {
  assistantState.evaluation = await apiFetch(assistantApi("/evaluation/report"), { method: "POST" });
  renderEvaluation();
  eventBus.emit("toast", t("rag.toast.reportReady"));
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
  eventBus.emit("toast", t("rag.toast.settingsSaved"));
}

function renderStatus() {
  const status = assistantState.status || {};
  const workspace = status.workspace || {};
  const kb = status.knowledge_base || {};
  setText("#rag-status-model", workspace.model_state || "--");
  const assistantEnabled = workspace.assistant_enabled ?? workspace.rag_enabled ?? true;
  setText("#rag-status-mode", assistantEnabled ? t("rag.mode.localSearch") : t("rag.mode.disabled"));
  setText("#rag-status-documents", kb.document_count ?? 0);
  setText("#rag-status-chunks", `${kb.indexed_chunk_count ?? 0}/${kb.chunk_count ?? 0}`);
  setText("#rag-status-index", formatIndexState(kb.index_state));
  setText("#rag-kb-badge", t("rag.docCount", { count: kb.document_count ?? 0 }));
  setText("#rag-agent-count", t("rag.runCount", { count: assistantState.agentRuns.length }));
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
    disabled: t("rag.settings.mode.disabled"),
    local_search_only: t("rag.settings.mode.localSearch"),
    local_gguf: t("rag.settings.mode.localGguf"),
    cloud_api: t("rag.settings.mode.cloudApi"),
  };
  return labels[mode] || mode || "--";
}

function renderKnowledgeBase() {
  const docs = assistantState.kb?.documents || [];
  const html = docs.length
    ? docs.map((doc) => `
      <article class="assistant-document-card">
        <strong>${escapeHtml(doc.filename)}</strong>
        <span>${escapeHtml(t("rag.chunkCount", { count: doc.chunk_count || 0 }))}</span>
        <code>${escapeHtml(formatIndexState(doc.index_state))}</code>
      </article>
    `).join("")
    : `<div class="empty-state">${escapeHtml(t("rag.noDocuments"))}</div>`;
  setHTML("#rag-document-list", html);
}

function formatIndexState(state) {
  const normalized = String(state || "unknown").toLowerCase();
  const labels = {
    empty: t("rag.indexState.empty"),
    indexed: t("rag.indexState.indexed"),
    ready: t("rag.indexState.ready"),
    stale: t("rag.indexState.stale"),
    unknown: t("rag.indexState.unknown"),
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
  setHTML("#rag-chat-answer", run?.answer ? escapeHtml(run.answer).replaceAll("\n", "<br>") : escapeHtml(t("rag.noAnswer")));
  setHTML("#rag-chat-sources", renderSourceList(run?.sources || []));
  setHTML("#rag-agent-trace", renderAgentTrace(run?.agent_trace || []));
}

function renderSourceList(sources = [], { allowMark = false, query = "" } = {}) {
  if (!sources.length) return `<div class="empty-state">${escapeHtml(t("rag.noSources"))}</div>`;
  return sources.map((source) => `
    <article class="assistant-source-card">
      <div class="assistant-source-head">
        <strong>${escapeHtml(source.source || source.document_id || "--")}</strong>
        <span>${escapeHtml(source.section || "")}</span>
        <code>${escapeHtml(String(source.score ?? "--"))}</code>
      </div>
      <p>${escapeHtml(source.content || "")}</p>
      ${allowMark ? `<button class="btn btn-secondary btn-sm" data-rag-mark-bad="${escapeHtml(source.chunk_id)}" data-rag-query="${escapeHtml(query)}">${escapeHtml(t("rag.markBad"))}</button>` : ""}
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
      eventBus.emit("toast", t("rag.toast.marked"));
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
  if (!steps.length) return `<div class="empty-state">${escapeHtml(t("rag.noTrace"))}</div>`;
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
      <code>${escapeHtml(t("rag.sourceCount", { count: run.sources?.length || 0 }))}</code>
    </article>
  `).join("") || `<div class="empty-state">${escapeHtml(t("rag.noRuns"))}</div>`);
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
    setHTML("#rag-evaluation-summary", `<div class="empty-state">${escapeHtml(t("rag.noReport"))}</div>`);
    return;
  }
  setHTML("#rag-evaluation-summary", `
    <div class="assistant-eval-grid">
      <div><span>${escapeHtml(t("rag.runs"))}</span><strong>${escapeHtml(report.run_count)}</strong></div>
      <div><span>${escapeHtml(t("rag.citationCoverage"))}</span><strong>${escapeHtml(report.citation_coverage)}</strong></div>
      <div><span>${escapeHtml(t("rag.sourceHitRate"))}</span><strong>${escapeHtml(report.source_hit_rate)}</strong></div>
      <div><span>${escapeHtml(t("rag.latency"))}</span><strong>${escapeHtml(report.average_latency_ms)} ms</strong></div>
    </div>
    <div class="path-row"><span>${escapeHtml(t("rag.reportPath"))}</span><code>${escapeHtml(report.report_path || "--")}</code></div>
  `);
}
