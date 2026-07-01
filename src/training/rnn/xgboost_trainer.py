from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


class XGBoostTrainingError(RuntimeError):
    pass


def train_xgboost_from_dataset(
    dataset: Dict[str, Any],
    run_dir: Path,
    config: Dict[str, Any],
    stop_requested=None,
    progress_callback=None,
) -> Dict[str, Any]:
    try:
        import xgboost as xgb
    except Exception as exc:
        raise XGBoostTrainingError(
            "XGBoost is required for sklearn_xgboost backend. Install package `xgboost` before training."
        ) from exc

    if stop_requested and stop_requested():
        raise XGBoostTrainingError("XGBoost training was stopped before fitting.")

    run_dir.mkdir(parents=True, exist_ok=True)
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)

    task_head = dataset["task_head"]
    is_regression = task_head == "regression"
    x_train = _flatten(dataset["tensors"]["train"]["x"])
    y_train = dataset["tensors"]["train"]["y"]
    x_val = _flatten(dataset["tensors"]["val"]["x"])
    y_val = dataset["tensors"]["val"]["y"]

    n_estimators = max(1, int(config.get("epochs") or config.get("n_estimators") or 100))
    learning_rate = float(config.get("lr0") or config.get("learning_rate") or 0.05)
    max_depth = max(1, int(config.get("max_depth") or 4))
    subsample = float(config.get("subsample") or 0.9)
    colsample_bytree = float(config.get("colsample_bytree") or 0.9)
    random_state = int(config.get("seed") or 42)

    common_params = {
        "learning_rate": learning_rate,
        "max_depth": max_depth,
        "subsample": subsample,
        "colsample_bytree": colsample_bytree,
        "seed": random_state,
        "n_jobs": max(1, int(config.get("workers") or 1)),
        "tree_method": "hist",
    }

    if is_regression:
        params = {"objective": "reg:squarederror", "eval_metric": "rmse", **common_params}
    else:
        params = {
            "objective": "multi:softprob" if int(dataset["num_outputs"]) > 2 else "binary:logistic",
            "eval_metric": "mlogloss" if int(dataset["num_outputs"]) > 2 else "logloss",
            **common_params,
        }
        if int(dataset["num_outputs"]) > 2:
            params["num_class"] = int(dataset["num_outputs"])

    dtrain = xgb.DMatrix(x_train, label=y_train)
    dval = xgb.DMatrix(x_val, label=y_val)
    evals_result: Dict[str, Dict[str, List[float]]] = {}
    model = xgb.train(
        params,
        dtrain,
        num_boost_round=n_estimators,
        evals=[(dtrain, "train"), (dval, "val")],
        evals_result=evals_result,
        verbose_eval=False,
    )

    history = _history_from_evals(evals_result)
    final_metrics = _evaluate_final(model, dval, y_val, is_regression, int(dataset["num_outputs"]))
    if history:
        history[-1].update(final_metrics)
    else:
        history = [{"epoch": 1, "train/loss": 0.0, "val/loss": 0.0, **final_metrics}]

    for row in history:
        if progress_callback:
            progress_callback(row)

    model.save_model(weights_dir / "best.json")
    model.save_model(weights_dir / "last.json")
    _write_model_metadata(weights_dir / "model_metadata.json", dataset, config, final_metrics)

    best_metric_key = "val/mae" if is_regression else "val/macro_f1"
    metrics_payload = {
        "backend": "sklearn_xgboost",
        "architecture": "rnn",
        "task_type": "sequence_regression" if is_regression else "sequence_classification",
        "primary_metric": best_metric_key,
        "history": history,
        "best_epoch": len(history),
        "best_metrics": history[-1],
        "dataset_summary": dataset["summary"],
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_csv(run_dir / "results.csv", history)
    return metrics_payload


def _flatten(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    return array.reshape(array.shape[0], -1)


def _history_from_evals(result: Dict[str, Dict[str, List[float]]]) -> List[Dict[str, Any]]:
    train_metrics = next(iter((result.get("train") or {}).values()), [])
    val_metrics = next(iter((result.get("val") or {}).values()), [])
    length = max(len(train_metrics), len(val_metrics))
    history: List[Dict[str, Any]] = []
    for index in range(length):
        history.append({
            "epoch": index + 1,
            "train/loss": round(float(train_metrics[index]), 6) if index < len(train_metrics) else 0.0,
            "val/loss": round(float(val_metrics[index]), 6) if index < len(val_metrics) else 0.0,
        })
    return history


def _evaluate_final(model: Any, dval: Any, y_val: np.ndarray, is_regression: bool, num_outputs: int) -> Dict[str, Any]:
    raw_predictions = model.predict(dval)
    if is_regression:
        errors = np.asarray(raw_predictions, dtype=float).reshape(-1) - np.asarray(y_val, dtype=float).reshape(-1)
        return {
            "val/mae": round(float(np.mean(np.abs(errors))), 6),
            "val/rmse": round(float(math.sqrt(np.mean(errors ** 2))), 6),
        }
    if num_outputs > 2:
        predictions = np.asarray(raw_predictions).argmax(axis=1)
    else:
        predictions = (np.asarray(raw_predictions).reshape(-1) >= 0.5).astype(int)
    return _classification_metrics(predictions.reshape(-1).tolist(), np.asarray(y_val).reshape(-1).tolist())


def _classification_metrics(predictions: List[Any], targets: List[Any]) -> Dict[str, float]:
    labels = sorted(set(predictions) | set(targets))
    total = len(targets) or 1
    accuracy = sum(1 for pred, target in zip(predictions, targets) if pred == target) / total
    precisions = []
    recalls = []
    f1s = []
    for label in labels:
        tp = sum(1 for pred, target in zip(predictions, targets) if pred == label and target == label)
        fp = sum(1 for pred, target in zip(predictions, targets) if pred == label and target != label)
        fn = sum(1 for pred, target in zip(predictions, targets) if pred != label and target == label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
    return {
        "val/accuracy": round(float(accuracy), 6),
        "val/precision": round(float(np.mean(precisions)) if precisions else 0.0, 6),
        "val/recall": round(float(np.mean(recalls)) if recalls else 0.0, 6),
        "val/macro_f1": round(float(np.mean(f1s)) if f1s else 0.0, 6),
    }


def _write_model_metadata(path: Path, dataset: Dict[str, Any], config: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    payload = {
        "backend": "sklearn_xgboost",
        "model": config.get("model") or "xgboost",
        "sequence_length": config.get("sequence_length"),
        "input_dim": dataset["input_dim"],
        "flattened_input_dim": int(dataset["input_dim"]) * int(dataset["summary"].get("sequence_length") or 1),
        "task_head": dataset["task_head"],
        "feature_columns": dataset["feature_columns"],
        "target_column": dataset["target_column"],
        "label_encoder": dataset.get("label_encoder"),
        "normalization": dataset["normalization"],
        "metrics": metrics,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_results_csv(path: Path, history: List[Dict[str, Any]]) -> None:
    if not history:
        return
    keys: List[str] = []
    for row in history:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(history)
