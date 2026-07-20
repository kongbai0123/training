import { escapeHtml } from "../utils.js";
import { appState, t } from "../state.js";
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

export function renderRnnModelGuideContent({ loading = false, guide = null } = {}) {
  if (loading) return renderRnnModelGuideLoading();
  if (!guide) return renderRnnModelGuideMissing();
  return renderRnnModelGuidePanel(guide);
}

export function renderRnnModelGuidePanel(guide = {}) {
  const localized = localizedGuide(guide);
  const statusClass = localized.status === "trainable" ? "badge-success" : "badge-warning";
  return `
    <div class="section-title">
      <h3>${escapeHtml(localized.title)}</h3>
      <span class="summary-badge ${statusClass}">${escapeHtml(localized.status === "trainable" ? t("rnn.guide.trainable") : t("rnn.guide.planned"))}</span>
    </div>
    <p>${escapeHtml(localized.summary)}</p>
    <div class="rnn-guide-grid">
      <div>
        <strong>${escapeHtml(t("rnn.guide.bestFor"))}</strong>
        <ul>${(localized.best_for || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>
      <div>
        <strong>${escapeHtml(t("rnn.guide.notFor"))}</strong>
        <ul>${(localized.not_for || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="rnn-guide-note"><span>${escapeHtml(t("rnn.guide.goodResult"))}</span><p>${escapeHtml(localized.good_result || "--")}</p></div>
    <div class="rnn-guide-note warning"><span>${escapeHtml(t("rnn.guide.risk"))}</span><p>${escapeHtml(localized.risk || "--")}</p></div>
  `;
}

function localizedGuide(guide) {
  if (appState.settings.language !== "en") return guide;
  const title = String(guide.title || "Sequence Model");
  const lower = title.toLowerCase();
  const regression = lower.includes("regression");
  const planned = guide.status !== "trainable";
  if (lower.includes("isolation forest")) {
    return {
      ...guide,
      summary: "A planned anomaly-detection baseline that flattens sequence windows for outlier scoring.",
      best_for: ["Finding suspicious segments with limited labels", "Datasets with many normal and few abnormal samples", "Comparing anomaly scores with an RNN classifier"],
      not_for: ["Supervised multi-class classification", "Continuous-value regression"],
      good_result: "Suspicious sequence windows receive the highest anomaly scores for human review.",
      risk: "Isolation Forest is neither an RNN nor a multi-class classifier, and its trainer is not connected yet.",
    };
  }
  if (lower.includes("xgboost")) {
    return {
      ...guide,
      summary: `A strong tabular baseline that flattens CSV sequence windows for ${regression ? "continuous-value regression" : "classification"}.`,
      best_for: ["Fixed-width tabular features", "Fast baseline experiments", "Sequences already represented by engineered statistics"],
      not_for: ["Learning long temporal dependencies directly", "End-to-end sequence tensor training"],
      good_result: regression ? "MAE and RMSE converge quickly to a stable baseline." : "Accuracy and Macro-F1 converge quickly and provide a useful RNN comparison.",
      risk: "XGBoost does not understand time order automatically; sequence windows must be converted into appropriate tabular features.",
    };
  }
  const bidirectional = lower.includes("bilstm");
  const lightweight = lower.includes("gru") || lower.includes("fastrnn");
  return {
    ...guide,
    summary: planned
      ? `A planned lightweight sequence ${regression ? "regression" : "classification"} model for lower training and inference cost.`
      : `${title} is suited to ordered ${regression ? "continuous-value prediction" : "class prediction"}${bidirectional ? " in offline workflows where the complete sequence is available" : ""}.`,
    best_for: bidirectional
      ? ["Offline analysis with complete sequences", "Tasks where context before and after an event matters", regression ? "Continuous targets influenced by neighboring time steps" : "Classification around state transitions"]
      : ["Ordered observations with temporal dependence", regression ? "Continuous numeric targets" : "State, event, or class prediction", lightweight ? "Faster baseline iteration" : "Medium-sized datasets with stable feature order"],
    not_for: bidirectional
      ? ["Real-time streaming prediction", "Deployments that can use only past observations"]
      : ["Rows that are independent with no time relationship", "Datasets with unstable or severely missing columns"],
    good_result: regression ? "Validation MAE and RMSE fall while predictions continue to follow real trends." : "Validation loss falls while Macro-F1 and Accuracy improve consistently.",
    risk: planned ? "The trainer is not connected yet; this entry is available for roadmap planning only." : (bidirectional ? "Future context can overstate results for real-time deployment." : "A window that is too short misses long dependencies; one that is too long can slow training or overfit."),
  };
}
