import { escapeHtml } from "../utils.js";

export function renderRnnPreviewTable(previewModel = {}) {
  return `<div class="rnn-preview-table-wrap"><table class="rnn-preview-table"><thead><tr>${(previewModel.columns || []).map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead><tbody>${(previewModel.rows || []).map((row) => `<tr>${(row || []).map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

export function renderRnnWindowSummaryRows(rows = []) {
  return rows
    .map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`)
    .join("");
}

export function renderRnnWindowWarning(messages = []) {
  if (!messages.length) return "";
  return `<strong>Window config</strong><span>${messages.map((item) => escapeHtml(item)).join("<br>")}</span>`;
}

export function renderRnnFeatureChipList(chips = []) {
  return chips
    .map((chip) => `<span class="rnn-chip ${chip.className}">${escapeHtml(chip.name)}${chip.exists ? "" : " \u7e5a missing"}</span>`)
    .join("");
}

export function renderRnnConfigMismatchWarning(mismatchSummary = {}) {
  return `<strong>${escapeHtml(mismatchSummary.title)}</strong><span>${escapeHtml(mismatchSummary.message)}</span>`;
}
