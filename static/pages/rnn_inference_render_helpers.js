import { escapeHtml } from "../utils.js";
import {
  formatRnnPredictionConfidence,
  rnnInferenceModelLabel
} from "./rnn_inference_helpers.js";

export function renderRnnInferenceModelOptions({ loading = false, models = [] } = {}) {
  if (loading) return `<option value="">Loading RNN models...</option>`;
  if (!models.length) return `<option value="">No RNN model found</option>`;
  return `<option value="">Select RNN model</option>${models.map((model) => {
    const label = rnnInferenceModelLabel(model);
    return `<option value="${escapeHtml(model.model_id)}">${escapeHtml(label)}</option>`;
  }).join("")}`;
}

export function renderRnnInferencePredictionRows(predictions = []) {
  return predictions.slice(0, 6).map((item) => {
    const confidence = formatRnnPredictionConfidence(item.confidence);
    return `<li><code>${escapeHtml(item.sequence_id)}</code> -> <strong>${escapeHtml(item.prediction)}</strong>${confidence}</li>`;
  }).join("") || "<li>No predictions returned.</li>";
}

export function renderRnnInferenceResultPanel(result = {}) {
  const summary = result.summary || {};
  const predictions = result.predictions || [];
  return `
    <div class="summary-row"><span>Job</span><code>${escapeHtml(result.job_id || "--")}</code></div>
    <div class="summary-row"><span>Sequences</span><code>${escapeHtml(summary.sequence_count ?? predictions.length)}</code></div>
    <div class="summary-row"><span>Latency</span><code>${escapeHtml(summary.inference_time_ms ?? "--")} ms</code></div>
    <ul class="rnn-inference-list">${renderRnnInferencePredictionRows(predictions)}</ul>
    <div class="inline-actions">
      ${result.urls?.prediction_json ? `<a class="btn btn-secondary btn-sm" target="_blank" href="${escapeHtml(result.urls.prediction_json)}">prediction.json</a>` : ""}
      ${result.urls?.prediction_csv ? `<a class="btn btn-secondary btn-sm" target="_blank" href="${escapeHtml(result.urls.prediction_csv)}">predictions.csv</a>` : ""}
    </div>
  `;
}
