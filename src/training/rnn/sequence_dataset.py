from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np

from src.project_layout import ProjectLayout
from src.training.rnn_config import active_rnn_config, compute_feature_config_hash
from src.training.rnn_readiness import ID_COLUMNS, META_COLUMNS, TARGET_COLUMNS, TIME_COLUMNS


class RNNSequenceDatasetError(ValueError):
    pass


def load_csv_feature_sequences(
    project: Dict[str, Any],
    sequence_length: int,
    stride: int,
    task_head: str = "classification",
) -> Dict[str, Any]:
    layout = ProjectLayout.from_project(project)
    sequences_dir = layout.sequences_dir()
    csv_files = sorted(sequences_dir.glob("*.csv")) if sequences_dir.exists() else []
    if not csv_files:
        raise RNNSequenceDatasetError("CSV feature sequence files are required under project/sequences.")

    config = active_rnn_config(project)
    rows, feature_columns, target_column, sequence_column, time_column = _read_csv_rows(csv_files, config)
    if not rows:
        raise RNNSequenceDatasetError("CSV feature sequence files contain no usable rows.")

    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        sequence_id = str(row.get(sequence_column) or "").strip() if sequence_column else "single_sequence"
        grouped[sequence_id or "single_sequence"].append(row)

    windows: List[Dict[str, Any]] = []
    for sequence_id, sequence_rows in grouped.items():
        ordered = _sort_sequence_rows(sequence_rows, time_column)
        split = _first_value(ordered, "split") or "unknown"
        for start in range(0, max(len(ordered) - sequence_length + 1, 0), max(stride, 1)):
            chunk = ordered[start : start + sequence_length]
            if len(chunk) < sequence_length:
                continue
            features = [[_float(row[col], col) for col in feature_columns] for row in chunk]
            target = chunk[-1].get(target_column)
            if target in (None, ""):
                continue
            windows.append(
                {
                    "sequence_id": sequence_id,
                    "split": split,
                    "features": features,
                    "target": target,
                    "start": start,
                }
            )

    if not windows:
        raise RNNSequenceDatasetError("No windows could be created from CSV feature sequences.")

    splits = _split_windows(windows)
    if not splits["train"] or not splits["val"]:
        raise RNNSequenceDatasetError("CSV feature sequences must include train and val splits.")

    train_features = np.asarray([item["features"] for item in splits["train"]], dtype=np.float32)
    mean = train_features.reshape(-1, train_features.shape[-1]).mean(axis=0)
    std = train_features.reshape(-1, train_features.shape[-1]).std(axis=0)
    std = np.where(std < 1e-8, 1.0, std)

    task_head = str(task_head or "classification").lower()
    is_regression = task_head == "regression"
    if is_regression:
        label_encoder = None
    else:
        labels = sorted({str(item["target"]) for item in windows})
        label_encoder = {label: idx for idx, label in enumerate(labels)}

    tensors: Dict[str, Dict[str, Any]] = {}
    for split_name, split_windows in splits.items():
        if not split_windows:
            continue
        x = np.asarray([item["features"] for item in split_windows], dtype=np.float32)
        x = (x - mean.reshape(1, 1, -1)) / std.reshape(1, 1, -1)
        if is_regression:
            y = np.asarray([_float(item["target"], target_column) for item in split_windows], dtype=np.float32)
        else:
            y = np.asarray([label_encoder[str(item["target"])] for item in split_windows], dtype=np.int64)
        tensors[split_name] = {
            "x": x,
            "y": y,
            "windows": split_windows,
        }

    return {
        "tensors": tensors,
        "feature_columns": feature_columns,
        "target_column": target_column,
        "sequence_column": sequence_column,
        "time_column": time_column,
        "input_dim": len(feature_columns),
        "task_head": "regression" if is_regression else "classification",
        "num_outputs": 1 if is_regression else len(label_encoder or {}),
        "label_encoder": label_encoder,
        "normalization": {
            "mean": mean.astype(float).tolist(),
            "std": std.astype(float).tolist(),
        },
        "summary": {
            "csv_files": [path.as_posix() for path in csv_files],
            "sequence_count": len(grouped),
            "window_count": len(windows),
            "split_counts": {key: len(value) for key, value in splits.items()},
            "sequence_length": sequence_length,
            "stride": stride,
            "feature_dim": len(feature_columns),
            "feature_config_hash": compute_feature_config_hash(config),
        },
        "feature_config_hash": compute_feature_config_hash(config),
    }


def write_preprocess_artifacts(run_dir: Path, dataset: Dict[str, Any]) -> None:
    preprocess_dir = run_dir / "preprocess"
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    (preprocess_dir / "feature_schema.json").write_text(
        json.dumps(
            {
                "feature_columns": dataset["feature_columns"],
                "target_column": dataset["target_column"],
                "sequence_column": dataset["sequence_column"],
                "time_column": dataset["time_column"],
                "input_dim": dataset["input_dim"],
                "task_head": dataset["task_head"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (preprocess_dir / "normalization_stats.json").write_text(
        json.dumps(dataset["normalization"], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if dataset.get("label_encoder") is not None:
        (preprocess_dir / "label_encoder.json").write_text(
            json.dumps(dataset["label_encoder"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _read_csv_rows(paths: Iterable[Path], config: Dict[str, Any] | None = None) -> Tuple[List[Dict[str, Any]], List[str], str, str, str | None]:
    all_rows: List[Dict[str, Any]] = []
    feature_columns: List[str] | None = None
    target_column: str | None = None
    sequence_column: str | None = None
    time_column: str | None = None
    config = config or {}
    configured_features = [str(col).strip() for col in config.get("feature_columns") or [] if str(col).strip()]
    configured_target = str(config.get("target_column") or "").strip()
    configured_sequence = str(config.get("sequence_column") or "").strip()
    configured_time = str(config.get("time_column") or "").strip()

    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            if not headers:
                continue
            current_sequence_col = configured_sequence or _first_present(headers, ID_COLUMNS) or ""
            current_target_col = configured_target or _first_present(headers, TARGET_COLUMNS)
            current_time_col = configured_time or _first_present(headers, TIME_COLUMNS)
            current_features = configured_features or [col for col in headers if col not in META_COLUMNS]
            if current_sequence_col and current_sequence_col not in headers:
                raise RNNSequenceDatasetError(f"{path.name} is missing sequence column: {current_sequence_col}.")
            if not current_target_col:
                raise RNNSequenceDatasetError(f"{path.name} must include label or target column.")
            if current_target_col not in headers:
                raise RNNSequenceDatasetError(f"{path.name} is missing target column: {current_target_col}.")
            if not current_features:
                raise RNNSequenceDatasetError(f"{path.name} must include at least one feature column.")
            missing_features = [col for col in current_features if col not in headers]
            if missing_features:
                raise RNNSequenceDatasetError(f"{path.name} is missing feature columns: {', '.join(missing_features)}.")
            if feature_columns is None:
                feature_columns = current_features
                target_column = current_target_col
                sequence_column = current_sequence_col
                time_column = current_time_col
            elif current_features != feature_columns:
                raise RNNSequenceDatasetError("All CSV feature files must use the same feature columns.")
            elif current_target_col != target_column or current_sequence_col != sequence_column:
                raise RNNSequenceDatasetError("All CSV feature files must use the same sequence and target columns.")
            for row in reader:
                if not current_sequence_col or str(row.get(current_sequence_col) or "").strip():
                    all_rows.append(row)

    if feature_columns is None or not target_column:
        raise RNNSequenceDatasetError("No valid CSV feature files were found.")
    return all_rows, feature_columns, target_column, sequence_column or "", time_column


def _split_windows(windows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    splits = {"train": [], "val": [], "test": []}
    for item in windows:
        split = str(item.get("split") or "unknown").lower()
        if split in {"validation", "valid"}:
            split = "val"
        if split in splits:
            splits[split].append(item)
    if not splits["train"] and not splits["val"] and windows:
        ordered = list(windows)
        train_end = max(1, int(len(ordered) * 0.7))
        val_end = max(train_end + 1, int(len(ordered) * 0.85)) if len(ordered) > 1 else train_end
        splits["train"] = ordered[:train_end]
        splits["val"] = ordered[train_end:val_end] or ordered[:1]
        splits["test"] = ordered[val_end:]
    return splits


def _sort_sequence_rows(rows: List[Dict[str, Any]], time_column: str | None) -> List[Dict[str, Any]]:
    if not time_column:
        return rows

    def key(row: Dict[str, Any]) -> tuple[int, float | str]:
        value = row.get(time_column)
        try:
            return (0, float(value))
        except (TypeError, ValueError):
            return (1, str(value or ""))

    return sorted(rows, key=key)


def _first_present(headers: Iterable[str], candidates: Iterable[str]) -> str | None:
    lowered = {header.lower(): header for header in headers}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _first_value(rows: Sequence[Dict[str, Any]], key: str) -> Any:
    for row in rows:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _float(value: Any, column: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RNNSequenceDatasetError(f"Column {column} contains non-numeric value: {value!r}") from exc
    if math.isnan(number) or math.isinf(number):
        raise RNNSequenceDatasetError(f"Column {column} contains invalid numeric value: {value!r}")
    return number
