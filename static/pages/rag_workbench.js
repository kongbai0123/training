import { apiFetch } from "../api.js";
import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { escapeHtml, qs, setHTML, setText } from "../utils.js";

const ragState = {
  status: null,
  kb: { documents: [], chunks: [] },
  profiles: [],
  retrieval: null,
  lastRun: null,
  agentRuns: [],
  sandbox: null,
  activeSandboxFile: "index.html",
  evaluation: null,
  conversationState: [],
};

export function initRagWorkbench() {
  qs("#btn-rag-refresh")?.addEventListener("click", () => loadRagWorkbench({ force: true }));
  qs("#btn-rag-ingest")?.addEventListener("click", ingestDocument);
  qs("#btn-rag-upload")?.addEventListener("click", uploadDocumentFile);
  qs("#btn-rag-reindex")?.addEventListener("click", reindexKnowledgeBase);
  qs("#btn-rag-clear-kb")?.addEventListener("click", clearKnowledgeBase);
  qs("#btn-rag-query")?.addEventListener("click", runRetrieval);
  qs("#btn-rag-chat")?.addEventListener("click", runRagChat);
  qs("#btn-rag-save-file")?.addEventListener("click", saveSandboxFile);
  qs("#btn-rag-export-artifact")?.addEventListener("click", exportSandboxArtifact);
  qs("#btn-rag-eval-report")?.addEventListener("click", generateEvaluationReport);
  qs("#rag-sandbox-file")?.addEventListener("change", (event) => {
    ragState.activeSandboxFile = event.target.value || "index.html";
    renderSandboxEditor();
  });
}

export function renderRagWorkbenchPage() {
  if (appState.currentPage !== "rag-workbench") return;
  if (!ragState.status) {
    loadRagWorkbench();
    return;
  }
  renderStatus();
  renderKnowledgeBase();
  renderProfiles();
  renderRetrievalResults();
  renderChatResult();
  renderAgentRuns();
  renderSandbox();
  renderEvaluation();
}

async function loadRagWorkbench({ force = false } = {}) {
  if (ragState.loading && !force) return;
  ragState.loading = true;
  try {
    const [status, kb, sandbox, runs] = await Promise.all([
      apiFetch("/api/rag-workbench/status"),
      apiFetch("/api/rag-workbench/knowledge-base"),
      apiFetch("/api/rag-workbench/sandbox"),
      apiFetch("/api/rag-workbench/agent-runs"),
    ]);
    ragState.status = status;
    ragState.kb = kb;
    ragState.profiles = status.retrieval_profiles || [];
    ragState.sandbox = sandbox;
    ragState.agentRuns = runs.runs || [];
    renderRagWorkbenchPage();
  } finally {
    ragState.loading = false;
  }
}

async function ingestDocument() {
  const filename = qs("#rag-doc-filename")?.value?.trim() || "rag-note.md";
  const content = qs("#rag-doc-content")?.value || "";
  if (!content.trim()) {
    eventBus.emit("toast", t("rag.toast.emptyDocument"));
    return;
  }
  const result = await apiFetch("/api/rag-workbench/knowledge-base/documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content }),
  });
  ragState.status = result.status;
  await loadRagWorkbench({ force: true });
  renderStages(result.document?.ingestion || []);
  eventBus.emit("toast", t("rag.toast.ingested", { count: result.document?.chunk_count || 0 }));
}

async function uploadDocumentFile() {
  const input = qs("#rag-upload-file");
  const file = input?.files?.[0];
  if (!file) {
    eventBus.emit("toast", t("rag.toast.noFile"));
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  const result = await apiFetch("/api/rag-workbench/knowledge-base/upload", {
    method: "POST",
    body: formData,
  });
  ragState.status = result.status;
  await loadRagWorkbench({ force: true });
  renderStages(result.document?.ingestion || []);
  eventBus.emit("toast", t("rag.toast.ingested", { count: result.document?.chunk_count || 0 }));
}

async function reindexKnowledgeBase() {
  ragState.status = await apiFetch("/api/rag-workbench/knowledge-base/reindex", { method: "POST" });
  await loadRagWorkbench({ force: true });
  eventBus.emit("toast", t("rag.toast.reindexed"));
}

async function clearKnowledgeBase() {
  const confirmed = window.confirm(t("rag.confirmClearKb"));
  if (!confirmed) return;
  ragState.status = await apiFetch("/api/rag-workbench/knowledge-base", { method: "DELETE" });
  ragState.retrieval = null;
  ragState.lastRun = null;
  await loadRagWorkbench({ force: true });
}

async function runRetrieval() {
  const query = qs("#rag-retrieval-query")?.value || "";
  if (!query.trim()) {
    eventBus.emit("toast", t("rag.toast.emptyQuery"));
    return;
  }
  ragState.retrieval = await apiFetch("/api/rag-workbench/retrieval/query", {
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

async function runRagChat() {
  const message = qs("#rag-chat-input")?.value || "";
  if (!message.trim()) {
    eventBus.emit("toast", t("rag.toast.emptyQuestion"));
    return;
  }
  ragState.lastRun = await apiFetch("/api/rag-workbench/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      conversation_state: ragState.conversationState,
      profile_id: qs("#rag-retrieval-profile")?.value || "lexical_default",
    }),
  });
  ragState.conversationState = ragState.lastRun.conversation_state || [];
  await loadRagWorkbench({ force: true });
  renderChatResult();
  renderAgentRuns();
}

async function saveSandboxFile() {
  const path = qs("#rag-sandbox-file")?.value || ragState.activeSandboxFile;
  const content = qs("#rag-sandbox-content")?.value || "";
  ragState.sandbox = await apiFetch("/api/rag-workbench/sandbox/files", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  renderSandbox();
  eventBus.emit("toast", t("rag.toast.fileSaved"));
}

async function exportSandboxArtifact() {
  const artifact = await apiFetch("/api/rag-workbench/sandbox/export", { method: "POST" });
  eventBus.emit("toast", t("rag.toast.artifactExported", { path: artifact.path || artifact.artifact_id }));
}

async function generateEvaluationReport() {
  ragState.evaluation = await apiFetch("/api/rag-workbench/evaluation/report", { method: "POST" });
  renderEvaluation();
  eventBus.emit("toast", t("rag.toast.reportReady"));
}

function renderStatus() {
  const status = ragState.status || {};
  const workspace = status.workspace || {};
  const kb = status.knowledge_base || {};
  setText("#rag-status-model", workspace.model_state || "--");
  setText("#rag-status-mode", workspace.rag_enabled ? "ON" : "OFF");
  setText("#rag-status-documents", kb.document_count ?? 0);
  setText("#rag-status-chunks", `${kb.indexed_chunk_count ?? 0}/${kb.chunk_count ?? 0}`);
  setText("#rag-status-index", formatIndexState(kb.index_state));
  setText("#rag-kb-badge", t("rag.docCount", { count: kb.document_count ?? 0 }));
  setText("#rag-agent-count", t("rag.runCount", { count: ragState.agentRuns.length }));
}

function renderKnowledgeBase() {
  const docs = ragState.kb?.documents || [];
  const html = docs.length
    ? docs.map((doc) => `
      <article class="rag-document-card">
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
    <div class="rag-stage ${escapeHtml(stage.state)}">
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
  select.innerHTML = (ragState.profiles || []).map((profile) => (
    `<option value="${escapeHtml(profile.profile_id)}">${escapeHtml(profile.name || profile.profile_id)}</option>`
  )).join("");
  select.value = [...select.options].some((option) => option.value === current) ? current : "lexical_default";
}

function renderRetrievalResults() {
  const results = ragState.retrieval?.results || [];
  setHTML("#rag-retrieval-results", renderSourceList(results, { allowMark: true, query: ragState.retrieval?.query || "" }));
  bindSourceMarkButtons();
}

function renderChatResult() {
  const run = ragState.lastRun;
  setHTML("#rag-chat-answer", run?.answer ? escapeHtml(run.answer).replaceAll("\n", "<br>") : escapeHtml(t("rag.noAnswer")));
  setHTML("#rag-chat-sources", renderSourceList(run?.sources || []));
  setHTML("#rag-agent-trace", renderAgentTrace(run?.agent_trace || []));
}

function renderSourceList(sources = [], { allowMark = false, query = "" } = {}) {
  if (!sources.length) return `<div class="empty-state">${escapeHtml(t("rag.noSources"))}</div>`;
  return sources.map((source) => `
    <article class="rag-source-card">
      <div class="rag-source-head">
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
      await apiFetch("/api/rag-workbench/retrieval/marks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: button.dataset.ragQuery || "",
          chunk_id: button.dataset.ragMarkBad,
          relevance: "bad",
          note: "Marked from Retrieval Workbench",
        }),
      });
      eventBus.emit("toast", t("rag.toast.marked"));
    }, { once: true });
  });
}

function renderAgentTrace(steps = []) {
  if (!steps.length) return `<div class="empty-state">${escapeHtml(t("rag.noTrace"))}</div>`;
  return steps.map((step) => `
    <div class="rag-agent-step ${escapeHtml(step.state || "pending")}">
      <strong>${escapeHtml(step.step || "--")}</strong>
      <span>${escapeHtml(step.message || "")}</span>
    </div>
  `).join("");
}

function renderAgentRuns() {
  setHTML("#rag-agent-runs", (ragState.agentRuns || []).slice(0, 6).map((run) => `
    <article class="rag-run-card">
      <strong>${escapeHtml(run.run_id)}</strong>
      <span>${escapeHtml(run.query || "")}</span>
      <code>${escapeHtml(t("rag.sourceCount", { count: run.sources?.length || 0 }))}</code>
    </article>
  `).join("") || `<div class="empty-state">${escapeHtml(t("rag.noRuns"))}</div>`);
}

function renderSandbox() {
  const sandbox = ragState.sandbox || {};
  const files = sandbox.files || [];
  const select = qs("#rag-sandbox-file");
  if (select) {
    const current = ragState.activeSandboxFile || select.value || "index.html";
    select.innerHTML = files.map((file) => `<option value="${escapeHtml(file.path)}">${escapeHtml(file.path)}</option>`).join("");
    select.value = files.some((file) => file.path === current) ? current : files[0]?.path || "index.html";
    ragState.activeSandboxFile = select.value;
  }
  renderSandboxEditor();
  const iframe = qs("#rag-sandbox-preview");
  if (iframe) iframe.srcdoc = sandbox.preview_html || "";
}

function renderSandboxEditor() {
  const path = ragState.activeSandboxFile || qs("#rag-sandbox-file")?.value || "index.html";
  const file = (ragState.sandbox?.files || []).find((item) => item.path === path);
  if (!file) return;
  const textarea = qs("#rag-sandbox-content");
  if (textarea && !textarea.matches(":focus")) textarea.value = file.content || "";
}

function renderEvaluation() {
  const report = ragState.evaluation;
  if (!report) {
    setHTML("#rag-evaluation-summary", `<div class="empty-state">${escapeHtml(t("rag.noReport"))}</div>`);
    return;
  }
  setHTML("#rag-evaluation-summary", `
    <div class="rag-eval-grid">
      <div><span>${escapeHtml(t("rag.runs"))}</span><strong>${escapeHtml(report.run_count)}</strong></div>
      <div><span>${escapeHtml(t("rag.citationCoverage"))}</span><strong>${escapeHtml(report.citation_coverage)}</strong></div>
      <div><span>${escapeHtml(t("rag.sourceHitRate"))}</span><strong>${escapeHtml(report.source_hit_rate)}</strong></div>
      <div><span>${escapeHtml(t("rag.latency"))}</span><strong>${escapeHtml(report.average_latency_ms)} ms</strong></div>
    </div>
    <div class="path-row"><span>${escapeHtml(t("rag.reportPath"))}</span><code>${escapeHtml(report.report_path || "--")}</code></div>
  `);
}
