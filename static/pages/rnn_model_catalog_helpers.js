export const RNN_MODEL_GROUPS = [
  ["pytorch_lstm", "RNN / Sequence"],
  ["pytorch_fastrnn", "RNN / Sequence · planned"],
  ["sklearn_xgboost", "Tabular Baseline"],
  ["sklearn_isolation_forest", "Anomaly Baseline · planned"]
];

export const RNN_MODEL_TOOLTIPS = {
  lstm: "LSTM uses input/forget/output gates and is the default choice for general CSV sequence learning.",
  gru: "GRU has fewer gates than LSTM, often trains faster, and is useful when data is limited.",
  bilstm: "BiLSTM reads the window in both directions. Use it for offline sequence tasks, not streaming inference.",
  fastrnn: "FastRNN is planned as a lightweight recurrent option. It is visible for roadmap clarity but not trainable yet.",
  xgboost_classifier: "XGBoost Classifier is a strong tabular baseline for sequence-window features.",
  xgboost_regressor: "XGBoost Regressor is a strong tabular baseline for numeric sequence targets.",
  isolation_forest: "Isolation Forest is planned for anomaly-oriented sequence-window baselines and is not trainable yet."
};

export function fallbackRnnModelCatalog() {
  return [
    { model_id: "fallback.rnn.lstm-classifier", display_name: "LSTM Classifier", backend: "pytorch_lstm", task_family: "sequence_classification", selector_value: "lstm", guide_key: "lstm_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.lstm-regressor", display_name: "LSTM Regressor", backend: "pytorch_lstm", task_family: "sequence_regression", selector_value: "lstm", guide_key: "lstm_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.gru-classifier", display_name: "GRU Classifier", backend: "pytorch_lstm", task_family: "sequence_classification", selector_value: "gru", guide_key: "gru_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.gru-regressor", display_name: "GRU Regressor", backend: "pytorch_lstm", task_family: "sequence_regression", selector_value: "gru", guide_key: "gru_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.bilstm-classifier", display_name: "BiLSTM Classifier", backend: "pytorch_lstm", task_family: "sequence_classification", selector_value: "bilstm", guide_key: "bilstm_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.bilstm-regressor", display_name: "BiLSTM Regressor", backend: "pytorch_lstm", task_family: "sequence_regression", selector_value: "bilstm", guide_key: "bilstm_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.rnn.fastrnn-classifier", display_name: "FastRNN Classifier", backend: "pytorch_fastrnn", task_family: "sequence_classification", selector_value: "fastrnn", guide_key: "fastrnn_classification", trainable: false, training_enabled: false, status: "planned" },
    { model_id: "fallback.rnn.fastrnn-regressor", display_name: "FastRNN Regressor", backend: "pytorch_fastrnn", task_family: "sequence_regression", selector_value: "fastrnn", guide_key: "fastrnn_regression", trainable: false, training_enabled: false, status: "planned" },
    { model_id: "fallback.xgboost.classifier", display_name: "XGBoost Classifier", backend: "sklearn_xgboost", task_family: "sequence_classification", selector_value: "xgboost_classifier", guide_key: "xgboost_classification", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.xgboost.regressor", display_name: "XGBoost Regressor", backend: "sklearn_xgboost", task_family: "sequence_regression", selector_value: "xgboost_regressor", guide_key: "xgboost_regression", trainable: true, training_enabled: true, status: "available" },
    { model_id: "fallback.isolation_forest.classifier", display_name: "Isolation Forest Baseline", backend: "sklearn_isolation_forest", task_family: "sequence_classification", selector_value: "isolation_forest", guide_key: "isolation_forest_classification", trainable: false, training_enabled: false, status: "planned" }
  ];
}

export function trainableTemplateRnnCatalog(catalog = []) {
  const baseCatalog = catalog.length ? catalog : fallbackRnnModelCatalog();
  const templates = baseCatalog.filter((model) => model.source !== "project_trained");
  return templates.length ? templates : fallbackRnnModelCatalog();
}

export function selectedRnnModelValue(entry, fallbackValue = "") {
  return entry?.selector_value || fallbackValue || "lstm";
}

export function resolveRnnModelEntry(catalog = [], value = "") {
  return catalog.find((model) => model.model_id === value || model.selector_value === value) || null;
}

export function selectedRnnBackend(entry, model = "") {
  return entry?.backend || (model.startsWith("xgboost") ? "sklearn_xgboost" : "pytorch_lstm");
}

export function selectedRnnBackendDisplay(entry, model = "") {
  const backend = selectedRnnBackend(entry, model);
  return entry?.training_enabled === false ? `${backend} (planned)` : backend;
}

export function resolveRnnGuideKey(entry, model, taskHead) {
  if (entry?.guide_key) return entry.guide_key;
  if (model === "xgboost_classifier") return "xgboost_classification";
  if (model === "xgboost_regressor") return "xgboost_regression";
  return `${model}_${taskHead}`;
}

export function isRnnModelTrainable(entry, model = "") {
  if (entry) return Boolean(entry.trainable && entry.training_enabled);
  return ["lstm", "gru", "bilstm"].includes(model);
}
