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
