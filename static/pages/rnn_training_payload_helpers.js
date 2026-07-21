function numberOrDefault(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function buildRnnTrainingPayload({
  backend = "pytorch_lstm",
  model = "lstm",
  taskHead = "classification",
  formValues = {}
} = {}) {
  return {
    backend,
    model,
    epochs: numberOrDefault(formValues.epochs, 10),
    batch_size: numberOrDefault(formValues.batchSize, 16),
    imgsz: 320,
    lr0: formValues.learningRateMode === "custom"
      ? numberOrDefault(formValues.learningRate, 0.001)
      : 0.001,
    lr0_mode: formValues.learningRateMode || "auto",
    optimizer: formValues.optimizer || "auto",
    device: formValues.device || "gpu",
    sequence_length: numberOrDefault(formValues.sequenceLength, 16),
    stride: numberOrDefault(formValues.stride, 8),
    horizon: numberOrDefault(formValues.horizon, 1),
    task_head: taskHead,
    hidden_size: numberOrDefault(formValues.hiddenSize, 128),
    num_layers: numberOrDefault(formValues.layers, 2),
    dropout: numberOrDefault(formValues.dropout, 0.2),
    bidirectional: model === "bilstm",
    gradient_clip_norm: numberOrDefault(formValues.gradientClipNorm, 0),
    early_stopping_patience: formValues.earlyStopEnabled === false
      ? 0
      : numberOrDefault(formValues.earlyStoppingPatience, 10)
  };
}
