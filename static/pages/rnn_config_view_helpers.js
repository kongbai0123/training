import { t } from "../state.js";

export function buildRnnDatasetBadge({ files = [], datasetImporting = false } = {}) {
  const count = Array.isArray(files) ? files.length : 0;
  return {
    badgeClass: count ? "badge-success" : "badge-warning",
    label: datasetImporting ? t("common.importing") : count ? `${count} CSV` : t("rnn.csvRequired")
  };
}

export function resolveRnnFeatureDimension({ config = {}, inspection = {} } = {}) {
  return (config.feature_columns || []).length || inspection.feature_dim || 0;
}

export function formatRnnFeatureConfigHash(config = {}) {
  return config.feature_config_hash
    ? t("rnn.features.hash", { hash: String(config.feature_config_hash).slice(0, 8) })
    : t("rnn.features.noConfig");
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
  const badgeLabel = status === "ok" ? t("common.ready") : status === "error" ? t("common.invalid") : t("rnn.csvRequired");
  const rows = [
    [t("rnn.window.estimatedWindows"), windowSummary.estimated_windows ?? "--"],
    [t("rnn.sequenceCount"), windowSummary.sequence_count ?? "--"],
    [t("rnn.window.minMaxLength"), `${windowSummary.min_sequence_length || "--"} / ${windowSummary.max_sequence_length || "--"}`]
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
    title: t("rnn.features.mismatchTitle"),
    message: t("rnn.features.mismatchMessage", { count })
  };
}
