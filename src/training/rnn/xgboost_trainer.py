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
    *,
    architecture: str = "rnn",
    task_prefix: str = "sequence",
    backend_name: str = "sklearn_xgboost",
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
    if x_train.shape[0] == 0:
        raise XGBoostTrainingError("XGBoost training requires at least one training row.")
    if x_val.shape[0] == 0:
        raise XGBoostTrainingError(
            "XGBoost training requires at least one validation row so model quality can be measured."
        )

    n_estimators = max(1, int(config.get("epochs") or config.get("n_estimators") or 100))
    # ``lr0`` remains required by the shared legacy request, but
    # ``learning_rate`` is the explicit XGBoost control and takes precedence.
    learning_rate_value = config.get("learning_rate")
    if learning_rate_value in (None, ""):
        learning_rate_value = config.get("lr0")
    learning_rate = float(
        learning_rate_value if learning_rate_value not in (None, "") else 0.05
    )
    max_depth = max(1, int(config.get("max_depth") or 4))
    subsample = float(config.get("subsample") or 0.9)
    colsample_bytree = float(config.get("colsample_bytree") or 0.9)
    seed_value = config.get("seed")
    random_state = int(seed_value if seed_value not in (None, "") else 42)

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
        params = {"objective": "reg:squarederror", "eval_metric": ["rmse", "mae"], **common_params}
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

    history = _history_from_evals(evals_result, is_regression=is_regression)
    final_metrics = _evaluate_final(model, dval, y_val, is_regression, int(dataset["num_outputs"]))
    diagnostics = final_metrics.pop("diagnostics", {})
    if history:
        history[-1].update(final_metrics)
    else:
        history = [{"epoch": 1, "train/loss": 0.0, "val/loss": 0.0, **final_metrics}]

    for row in history:
        if progress_callback:
            progress_callback(row)

    model.save_model(weights_dir / "best.json")
    model.save_model(weights_dir / "last.json")
    feature_importance = _feature_importance(
        model,
        dataset.get("feature_columns") or [],
        sequence_length=(
            max(1, int((dataset.get("summary") or {}).get("sequence_length") or 1))
            if architecture == "rnn"
            else 1
        ),
    )
    (run_dir / "feature_importance.json").write_text(
        json.dumps(feature_importance, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_model_metadata(
        weights_dir / "model_metadata.json",
        dataset,
        config,
        final_metrics,
        architecture=architecture,
        backend_name=backend_name,
        feature_importance=feature_importance,
    )

    best_metric_key = "val/mae" if is_regression else "val/macro_f1"
    metrics_payload = {
        "backend": backend_name,
        "architecture": architecture,
        "model": str(config.get("model") or ("xgboost_regressor" if is_regression else "xgboost_classifier")),
        "task_type": f"{task_prefix}_regression" if is_regression else f"{task_prefix}_classification",
        "primary_metric": best_metric_key,
        "history": history,
        "best_epoch": len(history),
        "best_metrics": history[-1],
        "dataset_summary": dataset["summary"],
        "feature_importance": feature_importance,
    }
    metrics_payload.update(diagnostics)
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_csv(run_dir / "results.csv", history)
    return metrics_payload


def _flatten(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float32)
    if array.shape[0] == 0:
        flattened_dim = int(np.prod(array.shape[1:])) if array.ndim > 1 else 1
        return np.empty((0, flattened_dim), dtype=np.float32)
    return array.reshape(array.shape[0], -1)


def _history_from_evals(
    result: Dict[str, Dict[str, List[float]]],
    is_regression: bool = False,
) -> List[Dict[str, Any]]:
    train_result = result.get("train") or {}
    val_result = result.get("val") or {}
    train_metrics = train_result.get("rmse") or next(iter(train_result.values()), [])
    val_metrics = val_result.get("rmse") or next(iter(val_result.values()), [])
    val_mae = val_result.get("mae") or []
    length = max(len(train_metrics), len(val_metrics))
    history: List[Dict[str, Any]] = []
    for index in range(length):
        row = {
            "epoch": index + 1,
            "train/loss": round(float(train_metrics[index]), 6) if index < len(train_metrics) else 0.0,
            "val/loss": round(float(val_metrics[index]), 6) if index < len(val_metrics) else 0.0,
        }
        if is_regression:
            row["val/rmse"] = row["val/loss"]
            if index < len(val_mae):
                row["val/mae"] = round(float(val_mae[index]), 6)
        history.append(row)
    return history


def _evaluate_final(model: Any, dval: Any, y_val: np.ndarray, is_regression: bool, num_outputs: int) -> Dict[str, Any]:
    raw_predictions = model.predict(dval)
    if is_regression:
        predictions = np.asarray(raw_predictions, dtype=float).reshape(-1).tolist()
        targets = np.asarray(y_val, dtype=float).reshape(-1).tolist()
        errors = np.asarray(predictions, dtype=float) - np.asarray(targets, dtype=float)
        target_array = np.asarray(targets, dtype=float)
        ss_res = float(np.sum(errors ** 2))
        ss_tot = float(np.sum((target_array - float(np.mean(target_array))) ** 2))
        return {
            "val/mae": round(float(np.mean(np.abs(errors))), 6),
            "val/rmse": round(float(math.sqrt(np.mean(errors ** 2))), 6),
            "val/r2": round(float(1.0 - (ss_res / ss_tot)), 6) if ss_tot > 0 else 0.0,
            "diagnostics": _diagnostics(predictions, targets, True),
        }
    if num_outputs > 2:
        predictions = np.asarray(raw_predictions).argmax(axis=1)
    else:
        predictions = (np.asarray(raw_predictions).reshape(-1) >= 0.5).astype(int)
    prediction_list = predictions.reshape(-1).tolist()
    target_list = np.asarray(y_val).reshape(-1).tolist()
    return {
        **_classification_metrics(prediction_list, target_list),
        "diagnostics": _diagnostics(prediction_list, target_list, False),
    }


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


def _diagnostics(predictions: List[Any], targets: List[Any], is_regression: bool, limit: int = 200) -> Dict[str, Any]:
    if is_regression:
        pairs = []
        residuals = []
        for pred, target in list(zip(predictions, targets))[:limit]:
            prediction = round(float(pred), 6)
            actual = round(float(target), 6)
            residual = round(prediction - actual, 6)
            pairs.append({"prediction": prediction, "actual": actual, "residual": residual})
            residuals.append(residual)
        return {
            "residuals": residuals,
            "prediction_actual_samples": pairs,
            "diagnostic_sample_limit": limit,
        }

    labels = sorted(set(predictions) | set(targets))
    label_index = {label: index for index, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for pred, target in zip(predictions, targets):
        if target in label_index and pred in label_index:
            matrix[label_index[target]][label_index[pred]] += 1
    return {
        "confusion_labels": [str(label) for label in labels],
        "confusion_matrix": matrix,
    }


def _write_model_metadata(
    path: Path,
    dataset: Dict[str, Any],
    config: Dict[str, Any],
    metrics: Dict[str, Any],
    *,
    architecture: str = "rnn",
    backend_name: str = "sklearn_xgboost",
    feature_importance: List[Dict[str, Any]] | None = None,
) -> None:
    payload = {
        "backend": backend_name,
        "architecture": architecture,
        "model": config.get("model") or "xgboost",
        "sequence_length": config.get("sequence_length") if architecture == "rnn" else None,
        "input_dim": dataset["input_dim"],
        "flattened_input_dim": int(dataset["input_dim"]) * int(dataset["summary"].get("sequence_length") or 1),
        "task_head": dataset["task_head"],
        "feature_columns": dataset["feature_columns"],
        "target_column": dataset["target_column"],
        "label_encoder": dataset.get("label_encoder"),
        "normalization": dataset.get("normalization") or {},
        "imputation": dataset.get("imputation") or {},
        "feature_importance": feature_importance or [],
        "metrics": metrics,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _feature_importance(
    model: Any,
    feature_columns: List[str],
    *,
    sequence_length: int = 1,
) -> List[Dict[str, Any]]:
    raw = model.get_score(importance_type="gain") or {}
    by_name = {str(name): 0.0 for name in feature_columns}
    flattened_feature_count = len(feature_columns) * max(1, int(sequence_length))
    for key, value in raw.items():
        name = key
        if key.startswith("f") and key[1:].isdigit():
            index = int(key[1:])
            if feature_columns and 0 <= index < flattened_feature_count:
                # RNN XGBoost flattens [time, feature] in row-major order.
                # Aggregate every timestep back into its original feature so
                # artifacts never leak opaque f2/f3/... names to users.
                name = feature_columns[index % len(feature_columns)]
        resolved_name = str(name)
        by_name[resolved_name] = by_name.get(resolved_name, 0.0) + float(value)
    rows = [
        {"feature": name, "gain": round(value, 8)}
        for name, value in by_name.items()
    ]
    rows.sort(key=lambda item: item["gain"], reverse=True)
    total = sum(float(item["gain"]) for item in rows)
    for item in rows:
        item["normalized_gain"] = round(float(item["gain"]) / total, 8) if total else 0.0
    return rows


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
