export function parseRnnFeatureColumns(value = "") {
  const seen = new Set();
  return String(value)
    .split(/[,;\n\r]+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

export function summarizeRnnReadiness(readiness = null) {
  const manifest = readiness?.summary?.manifest || {};
  const csv = readiness?.summary?.csv || {};
  const requirements = readiness?.summary?.ready_requirements || {};
  const source = readiness?.summary?.source || "none";
  const splitCounts = source === "manifest" ? manifest.split_counts || {} : csv.split_counts || {};
  const splitText = Object.keys(splitCounts).length
    ? Object.entries(splitCounts).map(([key, value]) => `${key}: ${value}`).join(" / ")
    : "-- / -- / --";
  const featureDim = csv.feature_dim || manifest.feature_dim || "--";
  const sequenceCount = csv.sequence_count || manifest.sequence_count || 0;
  const csvFiles = csv.file_count || 0;
  const requiredSequenceLength = Number(readiness?.sequence_length || 1);
  const csvMinLength = Number(csv.min_length || 0);

  return {
    manifest,
    csv,
    requirements,
    source,
    splitText,
    featureDim,
    sequenceCount,
    csvFiles,
    compactRows: [
      { label: "CSV", value: source === "csv" ? `${csvFiles} file(s)` : "Required", ok: source === "csv" },
      { label: "Features", value: csv.feature_dim ? `${csv.feature_dim} columns` : "--", ok: Boolean(csv.feature_dim) },
      { label: "Labels", value: csv.label_count ? `${csv.label_count} sequences` : "--", ok: Boolean(csv.label_count) },
      { label: "Split", value: splitText, ok: Boolean(requirements.train_val_split) },
      { label: "Window", value: `min ${csvMinLength} / need ${requiredSequenceLength}`, ok: csvMinLength >= requiredSequenceLength }
    ],
    requirementRows: [
      {
        label: "CSV source",
        ok: source === "csv",
        message: source === "csv"
          ? `${csvFiles} CSV file(s) detected.`
          : "Import CSV feature sequence files; manifest-only sources cannot start MVP training."
      },
      {
        label: "Feature columns",
        ok: Boolean(csv.feature_dim),
        message: csv.feature_dim ? `${csv.feature_dim} feature column(s) detected.` : "Configure at least one valid feature column."
      },
      {
        label: "Target labels",
        ok: Boolean(csv.label_count),
        message: csv.label_count ? `${csv.label_count} labeled sequence(s) detected.` : "CSV must include label/target values."
      },
      {
        label: "Train/Val split",
        ok: Boolean(requirements.train_val_split),
        message: splitText === "-- / -- / --" ? "CSV must include train and val split rows." : `Split counts: ${splitText}.`
      },
      {
        label: "Window length",
        ok: csvMinLength >= requiredSequenceLength,
        message: `Minimum length ${csvMinLength}; required ${requiredSequenceLength}.`
      }
    ]
  };
}

export function canStartRnnTrainingFromState({
  hasProject = false,
  modelTrainable = false,
  readiness = null,
  readinessLoading = false,
  trainingStarting = false,
  trainingStatus = ""
} = {}) {
  const csv = readiness?.summary?.csv || {};
  const isRunning = trainingStatus === "training" || trainingStatus === "stopping";
  return Boolean(
    hasProject &&
    modelTrainable &&
    readiness?.ready &&
    csv.valid &&
    Number(csv.file_count || 0) > 0 &&
    !readinessLoading &&
    !trainingStarting &&
    !isRunning
  );
}

export function rnnStartBlockerMessage({
  hasProject = false,
  readinessLoading = false,
  trainingStarting = false,
  trainingStatus = "",
  modelTrainable = false,
  modelLabel = "Selected model",
  readiness = null
} = {}) {
  if (!hasProject) return "Open a project before starting RNN training.";
  if (readinessLoading) return "RNN readiness is still checking.";
  if (trainingStarting) return "RNN training is starting.";
  if (trainingStatus === "training" || trainingStatus === "stopping") return "Another training job is already active.";
  if (!modelTrainable) {
    return `${modelLabel} is available in the catalog, but its training backend is not enabled yet.`;
  }
  if (!readiness) return "Run RNN readiness check before starting training.";
  const csv = readiness.summary?.csv || {};
  if (!csv.valid || Number(csv.file_count || 0) === 0) {
    return "RNNBackend MVP requires ready CSV feature sequence files under project/sequences.";
  }
  if (!readiness.ready) return readiness.message || "RNN readiness is not ready.";
  return "RNN training is disabled until readiness passes.";
}
