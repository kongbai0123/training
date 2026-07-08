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

export function resolveRnnInferenceControlRender(message = "") {
  const canRun = !message;
  return {
    disabled: !canRun,
    primaryActive: canRun,
    disabledActive: !canRun,
    reasonText: message || "Ready to run CSV sequence inference."
  };
}

export function renderRnnInferencePredictionRows(predictions = []) {
  return predictions.map((item) => {
    const confidence = formatRnnPredictionConfidence(item.confidence);
    const target = item.target !== undefined ? item.target : "--";
    const matched = item.target === undefined ? "--" : (String(item.prediction) === String(item.target) ? "Match" : "Mismatch");
    const rowClass = matched === "Mismatch" ? "is-mismatch" : "";
    const statusClass = matched === "Mismatch" ? "danger" : matched === "Match" ? "success" : "neutral";
    return `
      <tr class="${rowClass}">
        <td><code>${escapeHtml(item.sequence_id || "--")}</code></td>
        <td><strong>${escapeHtml(item.prediction ?? "--")}</strong></td>
        <td>${escapeHtml(confidence.replace(/[()]/g, "").trim() || "--")}</td>
        <td>${escapeHtml(target)}</td>
        <td><span class="rnn-inference-status ${statusClass}">${escapeHtml(matched)}</span></td>
      </tr>
    `;
  }).join("") || `<tr><td colspan="5">No predictions returned.</td></tr>`;
}

export function renderRnnInferenceResultPanel(result = {}) {
  const summary = result.summary || {};
  const predictions = result.predictions || [];
  const stats = buildRnnInferenceStats(predictions);
  const labels = Array.isArray(summary.predicted_labels) ? summary.predicted_labels.join(", ") : "--";
  const jobId = result.job_id || "--";
  const runId = summary.run_id || result.model?.run_id || "--";
  const outputFiles = renderRnnInferenceOutputFiles(result.urls || {});
  return `
    <div class="rnn-inference-result-panel">
      <div class="rnn-inference-overview">
        <div>
          <span class="rnn-inference-eyebrow">Latest sequence inference</span>
          <strong>${escapeHtml(stats.matchLabel)}</strong>
          <small>${escapeHtml(summary.sequence_count ?? predictions.length)} sequences processed</small>
        </div>
        <div class="rnn-inference-meta">
          <div><span>Job</span><code title="${escapeHtml(jobId)}">${escapeHtml(shortRnnInferenceId(jobId))}</code></div>
          <div><span>Run</span><code title="${escapeHtml(runId)}">${escapeHtml(shortRnnInferenceId(runId))}</code></div>
        </div>
      </div>
      <div class="rnn-inference-summary-grid">
        <div><span>Sequences</span><strong>${escapeHtml(summary.sequence_count ?? predictions.length)}</strong></div>
        <div><span>Latency</span><strong>${escapeHtml(summary.inference_time_ms ?? "--")} ms</strong></div>
        <div><span>Labels</span><strong>${escapeHtml(labels)}</strong></div>
        <div><span>Matched</span><strong>${escapeHtml(stats.matchLabel)}</strong></div>
      </div>
      <div class="rnn-inference-result-grid">
        <section>
          <div class="rnn-inference-result-heading">Prediction distribution</div>
          <div class="rnn-inference-distribution">${renderRnnInferenceDistribution(stats.predictionCounts)}</div>
        </section>
        <section>
          <div class="rnn-inference-result-heading">Target distribution</div>
          <div class="rnn-inference-distribution">${renderRnnInferenceDistribution(stats.targetCounts)}</div>
        </section>
        <section>
          <div class="rnn-inference-result-heading">Output files</div>
          <div class="rnn-inference-file-actions">${outputFiles}</div>
        </section>
      </div>
      <section class="rnn-inference-table-section">
        <div class="rnn-inference-section-header">
          <div>
            <div class="rnn-inference-result-heading">Prediction table</div>
            <p>Per-sequence prediction, confidence, target, and match status.</p>
          </div>
          <span>${escapeHtml(predictions.length)} rows</span>
        </div>
        <div class="rnn-inference-table-wrap rnn-inference-list">
          <table class="rnn-inference-table">
            <thead>
              <tr><th>Sequence</th><th>Prediction</th><th>Confidence</th><th>Target</th><th>Status</th></tr>
            </thead>
            <tbody>${renderRnnInferencePredictionRows(predictions)}</tbody>
          </table>
        </div>
      </section>
    </div>
  `;
}

function buildRnnInferenceStats(predictions = []) {
  const predictionCounts = {};
  const targetCounts = {};
  let comparable = 0;
  let matched = 0;

  predictions.forEach((item) => {
    const prediction = item.prediction ?? "--";
    predictionCounts[prediction] = (predictionCounts[prediction] || 0) + 1;
    if (item.target !== undefined) {
      comparable += 1;
      targetCounts[item.target] = (targetCounts[item.target] || 0) + 1;
      if (String(item.prediction) === String(item.target)) matched += 1;
    }
  });

  const matchLabel = comparable
    ? `${matched}/${comparable} (${((matched / comparable) * 100).toFixed(1)}%)`
    : "--";
  return { predictionCounts, targetCounts, matchLabel };
}

function renderRnnInferenceDistribution(counts = {}) {
  const entries = Object.entries(counts);
  if (!entries.length) return `<span class="rnn-inference-chip muted">No labels</span>`;
  return entries
    .sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))
    .map(([label, count]) => `
      <span class="rnn-inference-chip">
        <strong>${escapeHtml(label)}</strong>
        <code>${escapeHtml(count)}</code>
      </span>
    `)
    .join("");
}

function renderRnnInferenceOutputFiles(urls = {}) {
  const links = [
    ["prediction.json", urls.prediction_json],
    ["predictions.csv", urls.prediction_csv],
    ["summary.json", urls.summary_json]
  ].filter(([, url]) => url);
  if (!links.length) return `<span class="rnn-inference-chip muted">No output files</span>`;
  return links
    .map(([label, url]) => `<a class="btn btn-secondary btn-sm" target="_blank" href="${escapeHtml(url)}">${escapeHtml(label)}</a>`)
    .join("");
}

function shortRnnInferenceId(value = "") {
  const text = String(value || "--");
  if (text.length <= 30) return text;
  return `${text.slice(0, 18)}...${text.slice(-8)}`;
}
