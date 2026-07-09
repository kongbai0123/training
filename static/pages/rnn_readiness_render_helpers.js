import { escapeHtml } from "../utils.js";
import { t } from "../state.js";

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
    text: canStart ? t("common.ready") : loading ? t("common.checking") : readiness?.ready ? t("rnn.readiness.manifestOnly") : t("common.notReady")
  };
}

export function resolveRnnReadinessEmptyView(loading = false) {
  return {
    status: loading ? t("common.checking") : t("rnn.readiness.notReadyPreview"),
    message: loading
      ? t("rnn.readiness.checkingMessage")
      : t("rnn.readiness.emptyMessage")
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
    status: canStart ? t("rnn.readiness.csvTrainingEnabled") : readiness.ready ? t("rnn.readiness.readyCsvRequired") : t("common.notReady"),
    message: canStart
      ? t("rnn.readiness.readyMessage")
      : readiness.message || t("rnn.readiness.needsAttention"),
    modeBadge: canStart ? t("rnn.readiness.trainingEnabled") : t("rnn.readiness.csvRequired"),
    datasetMessage: canStart
      ? t("rnn.readiness.datasetReady", { count: sequenceCount })
      : t("rnn.readiness.datasetBlocked", { count: sequenceCount }),
    datasetPreview: source === "none"
      ? "sequence_id, timestep, feature_1, feature_2, target"
      : `source=${source}, feature_dim=${featureDim}, split=${splitText}`
  };
}

export function renderRnnStartBannerButtonContent(canStart = false) {
  return canStart
    ? `<i class="fa-solid fa-play"></i> ${escapeHtml(t("rnn.training.startShort"))}`
    : `<i class="fa-solid fa-lock"></i> ${escapeHtml(t("rnn.training.startDisabled"))}`;
}

export function resolveRnnTrainingActionText({ canStart = false, message = "" } = {}) {
  return canStart ? t("rnn.training.start") : message;
}

export function resolveRnnTrainingStateBadge({ canStart = false, modelTrainable = false } = {}) {
  return {
    className: `summary-badge ${canStart ? "badge-success" : "badge-warning"}`,
    text: canStart ? t("rnn.readiness.trainingEnabled") : modelTrainable ? t("rnn.readiness.required") : t("rnn.readiness.backendPlanned")
  };
}
