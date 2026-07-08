import { escapeHtml } from "../utils.js";
import { t } from "../state.js";
import {
  formatRnnPredictionConfidence,
  rnnInferenceModelLabel
} from "./rnn_inference_helpers.js";

export function renderRnnInferenceModelOptions({ loading = false, models = [] } = {}) {
  if (loading) return `<option value="">${escapeHtml(t("rnn.inference.loadingModels"))}</option>`;
  if (!models.length) return `<option value="">${escapeHtml(t("rnn.inference.noModelFound"))}</option>`;
  return `<option value="">${escapeHtml(t("rnn.inference.selectModel"))}</option>${models.map((model) => {
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
    reasonText: message || t("rnn.inference.readyToRun")
  };
}

export function renderRnnInferencePredictionRows(predictions = []) {
  return predictions.map((item) => {
    const confidence = formatRnnPredictionConfidence(item.confidence);
    const target = item.target !== undefined ? item.target : "--";
    const matchState = item.target === undefined ? "--" : (String(item.prediction) === String(item.target) ? "match" : "mismatch");
    const matched = matchState === "match" ? t("rnn.inference.match") : matchState === "mismatch" ? t("rnn.inference.mismatch") : "--";
    const rowClass = matchState === "mismatch" ? "is-mismatch" : "";
    const statusClass = matchState === "mismatch" ? "danger" : matchState === "match" ? "success" : "neutral";
    return `
      <tr class="${rowClass}">
        <td><code>${escapeHtml(item.sequence_id || "--")}</code></td>
        <td><strong>${escapeHtml(item.prediction ?? "--")}</strong></td>
        <td>${escapeHtml(confidence.replace(/[()]/g, "").trim() || "--")}</td>
        <td>${escapeHtml(target)}</td>
        <td><span class="rnn-inference-status ${statusClass}">${escapeHtml(matched)}</span></td>
      </tr>
    `;
  }).join("") || `<tr><td colspan="5">${escapeHtml(t("rnn.inference.noPredictions"))}</td></tr>`;
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
          <span class="rnn-inference-eyebrow">${escapeHtml(t("rnn.inference.latestSequenceInference"))}</span>
          <strong>${escapeHtml(stats.matchLabel)}</strong>
          <small>${escapeHtml(t("rnn.inference.sequencesProcessed", { count: summary.sequence_count ?? predictions.length }))}</small>
        </div>
        <div class="rnn-inference-meta">
          <div><span>${escapeHtml(t("rnn.inference.job"))}</span><code title="${escapeHtml(jobId)}">${escapeHtml(shortRnnInferenceId(jobId))}</code></div>
          <div><span>${escapeHtml(t("rnn.inference.run"))}</span><code title="${escapeHtml(runId)}">${escapeHtml(shortRnnInferenceId(runId))}</code></div>
        </div>
      </div>
      <div class="rnn-inference-summary-grid">
        <div><span>${escapeHtml(t("rnn.inference.sequences"))}</span><strong>${escapeHtml(summary.sequence_count ?? predictions.length)}</strong></div>
        <div><span>${escapeHtml(t("rnn.inference.latency"))}</span><strong>${escapeHtml(summary.inference_time_ms ?? "--")} ms</strong></div>
        <div><span>${escapeHtml(t("rnn.inference.labels"))}</span><strong>${escapeHtml(labels)}</strong></div>
        <div><span>${escapeHtml(t("rnn.inference.matched"))}</span><strong>${escapeHtml(stats.matchLabel)}</strong></div>
      </div>
      <div class="rnn-inference-result-grid">
        <section>
          <div class="rnn-inference-result-heading">${escapeHtml(t("rnn.inference.predictionDistribution"))}</div>
          <div class="rnn-inference-distribution">${renderRnnInferenceDistribution(stats.predictionCounts)}</div>
        </section>
        <section>
          <div class="rnn-inference-result-heading">${escapeHtml(t("rnn.inference.targetDistribution"))}</div>
          <div class="rnn-inference-distribution">${renderRnnInferenceDistribution(stats.targetCounts)}</div>
        </section>
        <section>
          <div class="rnn-inference-result-heading">${escapeHtml(t("rnn.inference.outputFiles"))}</div>
          <div class="rnn-inference-file-actions">${outputFiles}</div>
        </section>
      </div>
      <section class="rnn-inference-table-section">
        <div class="rnn-inference-section-header">
          <div>
            <div class="rnn-inference-result-heading">${escapeHtml(t("rnn.inference.predictionTable"))}</div>
            <p>${escapeHtml(t("rnn.inference.predictionTableHelp"))}</p>
          </div>
          <span>${escapeHtml(t("rnn.inference.rowCount", { count: predictions.length }))}</span>
        </div>
        <div class="rnn-inference-table-wrap rnn-inference-list">
          <table class="rnn-inference-table">
            <thead>
              <tr><th>${escapeHtml(t("rnn.inference.sequence"))}</th><th>${escapeHtml(t("rnn.inference.prediction"))}</th><th>${escapeHtml(t("rnn.inference.confidence"))}</th><th>${escapeHtml(t("common.target"))}</th><th>${escapeHtml(t("common.status"))}</th></tr>
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
  if (!entries.length) return `<span class="rnn-inference-chip muted">${escapeHtml(t("rnn.inference.noLabels"))}</span>`;
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
  if (!links.length) return `<span class="rnn-inference-chip muted">${escapeHtml(t("rnn.inference.noOutputFiles"))}</span>`;
  return links
    .map(([label, url]) => `<a class="btn btn-secondary btn-sm" target="_blank" href="${escapeHtml(url)}">${escapeHtml(label)}</a>`)
    .join("");
}

function shortRnnInferenceId(value = "") {
  const text = String(value || "--");
  if (text.length <= 30) return text;
  return `${text.slice(0, 18)}...${text.slice(-8)}`;
}
