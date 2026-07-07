export function buildRnnDatasetBadge({ files = [], datasetImporting = false } = {}) {
  const count = Array.isArray(files) ? files.length : 0;
  return {
    badgeClass: count ? "badge-success" : "badge-warning",
    label: datasetImporting ? "Importing" : count ? `${count} CSV` : "CSV required"
  };
}

export function resolveRnnFeatureDimension({ config = {}, inspection = {} } = {}) {
  return (config.feature_columns || []).length || inspection.feature_dim || 0;
}

export function formatRnnFeatureConfigHash(config = {}) {
  return config.feature_config_hash ? `hash ${String(config.feature_config_hash).slice(0, 8)}` : "No config";
}

export function buildRnnPreviewTableModel({ headers = [], rows = [] } = {}) {
  const previewRows = Array.isArray(rows) ? rows : [];
  const columns = Array.isArray(headers) ? headers.slice(0, 8) : [];
  return {
    hasRows: previewRows.length > 0,
    columns,
    rows: previewRows.slice(0, 6).map((row) => columns.map((column) => row?.[column] ?? "")),
    placeholder: "sequence_id, timestep, feature_1, feature_2, target"
  };
}

export function buildRnnFeatureChipModels({ features = [], headers = [], validation = null } = {}) {
  const availableHeaders = new Set(headers || []);
  const validationStatus = new Map((validation?.feature_status || []).map((item) => [item.name, item]));
  return features.map((name) => {
    const exists = validationStatus.get(name)?.exists ?? availableHeaders.has(name);
    return {
      name,
      exists,
      className: exists ? "valid" : "invalid"
    };
  });
}

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
