export function resolveRnnWindowSummary({
  validation = null,
  windowSummary = null,
  configValidation = null
} = {}) {
  return validation?.window || windowSummary || configValidation?.window || {};
}

export function buildRnnWindowSummaryRows(windowSummary = {}) {
  const status = windowSummary.status || "warning";
  const badgeClass = status === "ok" ? "badge-success" : status === "error" ? "badge-danger" : "badge-warning";
  const badgeLabel = status === "ok" ? "Ready" : status === "error" ? "Invalid" : "Needs CSV";
  const rows = [
    ["Estimated windows", windowSummary.estimated_windows ?? "--"],
    ["Sequence count", windowSummary.sequence_count ?? "--"],
    ["Min / Max length", `${windowSummary.min_sequence_length || "--"} / ${windowSummary.max_sequence_length || "--"}`]
  ];
  const messages = [...(windowSummary.errors || []), ...(windowSummary.warnings || [])];

  return {
    status,
    badgeClass,
    badgeLabel,
    rows,
    messages
  };
}

export function buildRnnMismatchSummary(mismatches = []) {
  const count = Array.isArray(mismatches) ? mismatches.length : 0;
  return {
    count,
    visible: count > 0,
    title: "Feature config mismatch",
    message: `${count} previous RNN run(s) use different feature config. Existing runs are kept, but direct comparison may be inconsistent.`
  };
}
