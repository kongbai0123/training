import { escapeHtml } from "../utils.js";

export function renderRnnReadinessCompactGrid(compactRows = []) {
  return compactRows.map((item) => {
    return `<div class="rnn-readiness-compact-item ${item.ok ? "success" : "danger"}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
    </div>`;
  }).join("");
}

export function buildRnnReadinessCheckRows(requirementRows = [], readinessChecks = []) {
  return [
    ...requirementRows.map((item) => ({
      label: item.label,
      status: item.ok ? "pass" : "fail",
      message: item.message
    })),
    ...(readinessChecks || [])
  ];
}

export function renderRnnReadinessCheckList(checks = []) {
  return checks.map((check) => {
    const statusClass = check.status === "pass" ? "success" : check.status === "warning" ? "warning" : "danger";
    return `<li class="rnn-readiness-item ${statusClass}">
      <strong>${escapeHtml(check.label || check.key)}</strong>
      <span>${escapeHtml(check.message || "")}</span>
    </li>`;
  }).join("");
}

export function resolveRnnReadinessBadge({ canStart = false, loading = false, readiness = null } = {}) {
  return {
    className: `summary-badge ${canStart ? "badge-success" : loading ? "badge-neutral" : "badge-warning"}`,
    text: canStart ? "Ready" : loading ? "Checking" : readiness?.ready ? "Manifest only" : "Not Ready"
  };
}

export function resolveRnnReadinessEmptyView(loading = false) {
  return {
    status: loading ? "Checking..." : "Not Ready / Preview",
    message: loading
      ? "Checking sequence manifest and CSV feature files..."
      : "Sequence CSV readiness summary appears here when a project is active."
  };
}

export function resolveRnnReadinessSummaryView({
  canStart = false,
  readiness = {},
  sequenceCount = 0,
  source = "none",
  featureDim = 0,
  splitText = ""
} = {}) {
  return {
    status: canStart ? "Ready / CSV training enabled" : readiness.ready ? "Ready but CSV required for training" : "Not Ready",
    message: canStart
      ? "Sequence CSV is ready for RNN training. Full checks are available only for diagnostics."
      : readiness.message || "Sequence dataset still needs attention. Open full checks for diagnostics.",
    modeBadge: canStart ? "Training enabled" : "CSV required",
    datasetMessage: canStart
      ? `${sequenceCount} sequence(s) detected from CSV. RNN training can start.`
      : `${sequenceCount} sequence(s) detected. CSV must include sequence id, target label/value, at least one feature column, train/val split, and enough rows for sequence_length.`,
    datasetPreview: source === "none"
      ? "sequence_id, timestep, feature_1, feature_2, target"
      : `source=${source}, feature_dim=${featureDim}, split=${splitText}`
  };
}

export function renderRnnStartBannerButtonContent(canStart = false) {
  return canStart
    ? `<i class="fa-solid fa-play"></i> Start RNN`
    : `<i class="fa-solid fa-lock"></i> Start RNN Disabled`;
}

export function resolveRnnTrainingActionText({ canStart = false, message = "" } = {}) {
  return canStart ? "Start RNN Training" : message;
}

export function resolveRnnTrainingStateBadge({ canStart = false, modelTrainable = false } = {}) {
  return {
    className: `summary-badge ${canStart ? "badge-success" : "badge-warning"}`,
    text: canStart ? "Training enabled" : modelTrainable ? "Readiness required" : "Backend planned"
  };
}
