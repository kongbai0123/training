export function canonicalMetricKey(value) {
  const raw = String(value || "").toLowerCase();
  const compact = raw.replace(/[^a-z0-9]+/g, "");
  if (!compact) return "";
  if (compact.includes("map")) {
    const mask = raw.includes("(m)") || compact.includes("mask") || compact.includes("seg");
    const box = raw.includes("(b)") || compact.includes("box") || compact.includes("detect");
    const range = compact.includes("5095") ? "50_95" : compact.includes("50") ? "50" : "";
    return `${mask ? "mask" : box ? "box" : "map"}_map${range ? `_${range}` : ""}`;
  }
  if (compact.includes("macrof1")) return "macro_f1";
  if (compact === "f1" || compact.includes("f1score")) return "f1";
  if (compact.includes("accuracy") || compact === "acc") return "accuracy";
  if (compact.includes("precision")) return "precision";
  if (compact.includes("recall")) return "recall";
  if (compact.includes("rmse")) return "rmse";
  if (compact.includes("mae")) return "mae";
  if (compact.includes("r2")) return "r2";
  return compact;
}

export function sameMetric(left, right) {
  const canonicalLeft = canonicalMetricKey(left);
  const canonicalRight = canonicalMetricKey(right);
  return Boolean(canonicalLeft && canonicalRight && canonicalLeft === canonicalRight);
}

export function isPercentMetric(key) {
  return ["mask_map_50_95", "mask_map_50", "box_map_50_95", "box_map_50", "map_map_50_95", "map_map_50", "macro_f1", "f1", "accuracy", "precision", "recall"].includes(canonicalMetricKey(key));
}

export function normalizedMetricValue(value, key) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return isPercentMetric(key) && Math.abs(number) <= 1 ? number * 100 : number;
}

export function normalizeModelIdentity(value) {
  const filename = String(value || "").split(/[\\/]/).pop() || "";
  return filename
    .toLowerCase()
    .replace(/\.(pt|pth|onnx|yaml|yml|zip)$/i, "")
    .replace(/^(builtin|template|imported)[._-]+/, "")
    .replace(/[._-]+/g, "")
    .replace(/recommended$/g, "")
    .replace(/(segmentation|detection|classifier|regressor)$/g, (token) => ({ segmentation: "seg", detection: "det", classifier: "", regressor: "" }[token]));
}

export function normalizeTaskFamily(value) {
  const task = String(value || "").toLowerCase();
  if (task.includes("seg")) return "segmentation";
  if (task.includes("detect")) return "detection";
  if (task.includes("regression")) return "sequence_regression";
  if (task.includes("sequence") || task.includes("classification")) return "sequence_classification";
  return task;
}

export function modelMatchesRun(model, run) {
  const candidates = new Set([model.model_id, model.display_name, model.weight, model.selector_value, model.training_value]
    .filter(Boolean).map(normalizeModelIdentity).filter(Boolean));
  const runModel = normalizeModelIdentity(run.model || "");
  const modelTask = normalizeTaskFamily(model.task_family);
  const runTask = normalizeTaskFamily(run.task_family || run.task_type);
  const taskMatches = !modelTask || !runTask || modelTask === runTask;
  return Boolean(taskMatches && runModel && [...candidates].some((candidate) => candidate.length > 2 && runModel === candidate));
}
