export function filterRnnInferenceModels(models = [], backend = "pytorch_lstm") {
  return (Array.isArray(models) ? models : []).filter((model) =>
    model.architecture === "rnn" || model.backend === backend
  );
}

export function rnnInferenceModelLabel(model = {}) {
  return `${model.run_id || "run"} / ${model.weight_type || "weight"} / ${model.model_name || "RNN"}`;
}

export function resolveRnnInferenceModelValue(models = [], current = "") {
  if (models.some((model) => model.model_id === current)) {
    return current;
  }
  const firstReady = models.find((model) => model.status === "ready");
  return (firstReady || models[0])?.model_id || "";
}

export function rnnInferenceBlockerMessage({
  hasProject,
  isLoading,
  isRunning,
  selectedModel,
  hasFile,
  trusted,
  hasPath
} = {}) {
  if (!hasProject) return "Open a project before sequence inference.";
  if (isLoading) return "Loading RNN models.";
  if (isRunning) return "Sequence inference is running.";
  if (!selectedModel) return "Select an RNN model.";
  if (!hasFile && !hasPath) {
    return trusted ? "Provide a CSV feature sequence file or project CSV path." : "Upload a CSV feature sequence file.";
  }
  return "";
}

export function formatRnnPredictionConfidence(confidence) {
  return confidence !== undefined ? ` (${Number(confidence).toFixed(3)})` : "";
}
