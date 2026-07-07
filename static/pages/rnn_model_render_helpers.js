import { escapeHtml } from "../utils.js";
import { RNN_MODEL_GROUPS } from "./rnn_model_catalog_helpers.js";

export function renderRnnModelSelectorOptions({
  loading = false,
  models = []
} = {}) {
  if (!models.length) return `<option value="">No compatible RNN model found</option>`;
  const loadingOption = loading
    ? `<option value="" disabled>Loading catalog in background...</option>`
    : "";
  return loadingOption + RNN_MODEL_GROUPS.map(([backend, label]) => {
    const items = models.filter((model) => model.backend === backend);
    if (!items.length) return "";
    return `<optgroup label="${escapeHtml(label)}">${items.map((model) => {
      const suffix = model.training_enabled ? "" : " · planned";
      return `<option value="${escapeHtml(model.model_id)}">${escapeHtml(model.display_name || model.model_id)}${suffix}</option>`;
    }).join("")}</optgroup>`;
  }).join("");
}

export function renderRnnModelGuideLoading() {
  return `<div class="section-title"><h3>Model Guide</h3><span class="summary-badge badge-neutral">Loading</span></div><p>Loading model guide...</p>`;
}

export function renderRnnModelGuideMissing() {
  return `<div class="section-title"><h3>Model Guide</h3><span class="summary-badge badge-warning">Missing</span></div><p>No guide found for this model/task combination.</p>`;
}

export function renderRnnModelGuidePanel(guide = {}) {
  const statusClass = guide.status === "trainable" ? "badge-success" : "badge-warning";
  return `
    <div class="section-title">
      <h3>${escapeHtml(guide.title)}</h3>
      <span class="summary-badge ${statusClass}">${escapeHtml(guide.status === "trainable" ? "Trainable" : "Planned")}</span>
    </div>
    <p>${escapeHtml(guide.summary)}</p>
    <div class="rnn-guide-grid">
      <div>
        <strong>適合</strong>
        <ul>${(guide.best_for || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>
      <div>
        <strong>不適合</strong>
        <ul>${(guide.not_for || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="rnn-guide-note"><span>好結果通常長這樣</span><p>${escapeHtml(guide.good_result || "--")}</p></div>
    <div class="rnn-guide-note warning"><span>風險</span><p>${escapeHtml(guide.risk || "--")}</p></div>
  `;
}
