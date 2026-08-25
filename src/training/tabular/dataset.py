from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np


TABULAR_DATASET_SCHEMA_VERSION = "1.0"
DEFAULT_MISSING_TOKENS = ("", "?", "na", "n/a", "nan", "none", "null")
_SPLIT_NAMES = ("train", "val", "test")
_SPLIT_ALIASES = {
    "train": "train",
    "training": "train",
    "val": "val",
    "valid": "val",
    "validation": "val",
    "dev": "val",
    "test": "test",
    "testing": "test",
}


class TabularDatasetError(ValueError):
    """Raised when a CSV cannot satisfy the row-level tabular contract."""


def load_csv_tabular_dataset(
    csv_path: str | Path,
    *,
    target_column: str,
    feature_columns: Sequence[str] | None = None,
    split_column: str | None = None,
    task_head: str = "classification",
    seed: int = 42,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> Dict[str, Any]:
    """Load one CSV as a deterministic, row-level tabular dataset.

    Only numeric feature columns are accepted. Missing feature values are
    imputed with medians fitted on the training split; target values are never
    imputed. If no split column is supplied, classification is stratified by
    label and regression is randomly split with ``seed``.

    A CSV column named ``split`` is detected automatically. Set
    ``split_column`` explicitly when another column name is used.
    """

    source_path = Path(csv_path)
    if not source_path.is_file():
        raise TabularDatasetError(f"Tabular CSV file does not exist: {source_path}")
    if source_path.suffix.lower() != ".csv":
        raise TabularDatasetError(f"Tabular dataset must be a CSV file: {source_path.name}")

    normalized_task = str(task_head or "").strip().lower()
    if normalized_task not in {"classification", "regression"}:
        raise TabularDatasetError("task_head must be either 'classification' or 'regression'.")
    normalized_seed = _validate_seed(seed)
    ratios = _validate_ratios(train_ratio, val_ratio, test_ratio)

    headers, raw_rows = _read_csv(source_path)
    actual_target = _resolve_column(headers, target_column, "target")
    requested_split = str(split_column or "").strip()
    if requested_split:
        actual_split = _resolve_column(headers, requested_split, "split")
    else:
        actual_split = _find_column(headers, "split")

    if feature_columns is None:
        actual_features = [
            column for column in headers if column != actual_target and column != actual_split
        ]
    else:
        actual_features = [
            _resolve_column(headers, str(column), "feature") for column in feature_columns
        ]
    _validate_feature_columns(actual_features, actual_target, actual_split)

    records: List[Dict[str, Any]] = []
    missing_counts = {column: 0 for column in actual_features}
    for record_index, (source_row_number, row) in enumerate(raw_rows):
        parsed_features: List[float | None] = []
        for column in actual_features:
            value = _parse_feature(row.get(column), column, source_row_number)
            if value is None:
                missing_counts[column] += 1
            parsed_features.append(value)

        parsed_target = _parse_target(
            row.get(actual_target),
            actual_target,
            source_row_number,
            normalized_task,
        )
        parsed_split = (
            _parse_split(row.get(actual_split), actual_split, source_row_number)
            if actual_split
            else None
        )
        records.append(
            {
                "record_index": record_index,
                "source_row_number": source_row_number,
                "features": parsed_features,
                "target": parsed_target,
                "split": parsed_split,
            }
        )

    if not records:
        raise TabularDatasetError("Tabular CSV contains no usable data rows.")

    if normalized_task == "classification":
        labels = sorted({str(record["target"]) for record in records})
        if len(labels) < 2:
            raise TabularDatasetError("Classification requires at least two distinct target labels.")
        label_encoder: Dict[str, int] | None = {
            label: index for index, label in enumerate(labels)
        }
    else:
        labels = []
        label_encoder = None

    if actual_split:
        split_indices = _provided_split_indices(records)
        split_method = "provided"
    elif normalized_task == "classification":
        split_indices = _stratified_split_indices(
            [str(record["target"]) for record in records],
            ratios,
            normalized_seed,
        )
        split_method = "stratified"
    else:
        split_indices = _random_split_indices(len(records), ratios, normalized_seed)
        split_method = "random"

    if not split_indices["train"]:
        raise TabularDatasetError("The tabular dataset must contain at least one training row.")

    train_missing_labels: List[str] = []
    if normalized_task == "classification":
        train_labels = {str(records[index]["target"]) for index in split_indices["train"]}
        train_missing_labels = [label for label in labels if label not in train_labels]
        if train_missing_labels:
            missing = ", ".join(repr(label) for label in train_missing_labels)
            raise TabularDatasetError(
                "The training split is missing target labels present in the overall dataset: "
                f"{missing}. Move at least one row for each missing label into the training split."
            )

    medians = _training_medians(records, split_indices["train"], actual_features)
    tensors = _build_tensors(
        records,
        split_indices,
        medians,
        normalized_task,
        label_encoder,
    )

    config_payload = {
        "schema_version": TABULAR_DATASET_SCHEMA_VERSION,
        "architecture": "tabular",
        "feature_columns": actual_features,
        "target_column": actual_target,
        "split_column": actual_split,
        "task_head": normalized_task,
        "seed": normalized_seed,
        "split_ratios": dict(zip(_SPLIT_NAMES, ratios)),
        "split_method": split_method,
        "imputation": {"strategy": "median", "fit_split": "train"},
    }
    feature_config_hash = _canonical_hash(config_payload)
    source_hash = _file_sha256(source_path)
    split_counts = {name: len(indices) for name, indices in split_indices.items()}
    actual_ratios = {
        name: round(count / len(records), 8) for name, count in split_counts.items()
    }

    class_counts: Dict[str, int] = {}
    if normalized_task == "classification":
        class_counts = dict(sorted(_counts(str(record["target"]) for record in records).items()))

    imputation = {
        "schema_version": TABULAR_DATASET_SCHEMA_VERSION,
        "strategy": "median",
        "fit_split": "train",
        "statistics": medians,
        "missing_tokens": list(DEFAULT_MISSING_TOKENS),
    }
    summary = {
        "schema_version": TABULAR_DATASET_SCHEMA_VERSION,
        "architecture": "tabular",
        "source": {
            "file_name": source_path.name,
            "size_bytes": source_path.stat().st_size,
            "sha256": source_hash,
        },
        "dataset_hash": source_hash,
        "row_count": len(records),
        "feature_dim": len(actual_features),
        "feature_columns": actual_features,
        "target_column": actual_target,
        "split_column": actual_split,
        "task_head": normalized_task,
        "num_outputs": 1 if normalized_task == "regression" else len(labels),
        "split_method": split_method,
        "split_counts": split_counts,
        "requested_split_ratios": dict(zip(_SPLIT_NAMES, ratios)),
        "actual_split_ratios": actual_ratios,
        "seed": normalized_seed,
        "missing_feature_values": missing_counts,
        "imputed_value_count": sum(missing_counts.values()),
        "class_counts": class_counts,
        "train_missing_labels": train_missing_labels,
        "feature_config_hash": feature_config_hash,
    }

    return {
        "tensors": tensors,
        "feature_columns": actual_features,
        "target_column": actual_target,
        "split_column": actual_split,
        "input_dim": len(actual_features),
        "task_head": normalized_task,
        "num_outputs": 1 if normalized_task == "regression" else len(labels),
        "label_encoder": label_encoder,
        "imputation": imputation,
        "summary": summary,
        "feature_config_hash": feature_config_hash,
        "dataset_hash": source_hash,
    }


def write_preprocess_artifacts(run_dir: Path, dataset: Mapping[str, Any]) -> None:
    """Write the portable preprocessing contract required for inference."""

    required = (
        "feature_columns",
        "target_column",
        "task_head",
        "num_outputs",
        "imputation",
        "feature_config_hash",
    )
    missing = [key for key in required if key not in dataset]
    if missing:
        raise TabularDatasetError(
            f"Tabular dataset is missing preprocessing fields: {', '.join(missing)}."
        )

    feature_columns = [str(column) for column in dataset["feature_columns"]]
    preprocess_dir = Path(run_dir) / "preprocess"
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    feature_schema = {
        "schema_version": TABULAR_DATASET_SCHEMA_VERSION,
        "architecture": "tabular",
        "feature_columns": feature_columns,
        "target_column": dataset["target_column"],
        "split_column": dataset.get("split_column"),
        "input_dim": len(feature_columns),
        "task_head": dataset["task_head"],
        "num_outputs": int(dataset["num_outputs"]),
        "feature_dtypes": {column: "float32" for column in feature_columns},
        "feature_config_hash": dataset["feature_config_hash"],
    }
    _write_json(preprocess_dir / "feature_schema.json", feature_schema)
    _write_json(preprocess_dir / "imputation.json", dataset["imputation"])

    label_encoder = dataset.get("label_encoder")
    if label_encoder is not None:
        ordered_classes = [
            label for label, _ in sorted(label_encoder.items(), key=lambda item: int(item[1]))
        ]
        _write_json(
            preprocess_dir / "label_encoder.json",
            {
                "schema_version": TABULAR_DATASET_SCHEMA_VERSION,
                "classes": ordered_classes,
                "mapping": dict(label_encoder),
            },
        )


def _read_csv(path: Path) -> Tuple[List[str], List[Tuple[int, Dict[str, Any]]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            raw_headers = reader.fieldnames or []
            headers = [str(header or "").strip() for header in raw_headers]
            if not headers:
                raise TabularDatasetError("Tabular CSV must include a header row.")
            if any(not header for header in headers):
                raise TabularDatasetError("Tabular CSV contains an empty column name.")
            duplicate_headers = sorted(
                header for header, count in _counts(headers).items() if count > 1
            )
            if duplicate_headers:
                raise TabularDatasetError(
                    f"Tabular CSV contains duplicate columns: {', '.join(duplicate_headers)}."
                )
            reader.fieldnames = headers
            rows: List[Tuple[int, Dict[str, Any]]] = []
            for source_row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise TabularDatasetError(
                        f"CSV row {source_row_number} has more values than the header."
                    )
                if all(str(value or "").strip() == "" for value in row.values()):
                    continue
                rows.append((source_row_number, row))
            return headers, rows
    except TabularDatasetError:
        raise
    except UnicodeDecodeError as exc:
        raise TabularDatasetError(
            f"Tabular CSV must use UTF-8 encoding: {path.name}"
        ) from exc
    except (OSError, csv.Error) as exc:
        raise TabularDatasetError(f"Could not read tabular CSV {path.name}: {exc}") from exc


def _resolve_column(headers: Sequence[str], requested: str, role: str) -> str:
    name = str(requested or "").strip()
    if not name:
        raise TabularDatasetError(f"A {role} column must be selected.")
    if name in headers:
        return name
    lowered = [header for header in headers if header.lower() == name.lower()]
    if len(lowered) == 1:
        return lowered[0]
    raise TabularDatasetError(f"Tabular CSV is missing {role} column: {name}.")


def _find_column(headers: Sequence[str], requested: str) -> str | None:
    lowered = requested.lower()
    for header in headers:
        if header.lower() == lowered:
            return header
    return None


def _validate_feature_columns(
    feature_columns: Sequence[str], target_column: str, split_column: str | None
) -> None:
    if not feature_columns:
        raise TabularDatasetError("At least one numeric feature column is required.")
    duplicates = sorted(
        column for column, count in _counts(feature_columns).items() if count > 1
    )
    if duplicates:
        raise TabularDatasetError(
            f"Feature columns must be unique: {', '.join(duplicates)}."
        )
    reserved = {target_column}
    if split_column:
        reserved.add(split_column)
    invalid = [column for column in feature_columns if column in reserved]
    if invalid:
        raise TabularDatasetError(
            f"Target and split columns cannot be features: {', '.join(invalid)}."
        )


def _parse_feature(value: Any, column: str, row_number: int) -> float | None:
    text = str(value or "").strip()
    if text.lower() in DEFAULT_MISSING_TOKENS:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise TabularDatasetError(
            f"Feature column {column} contains a non-numeric value at CSV row "
            f"{row_number}: {value!r}."
        ) from exc
    if math.isnan(number):
        return None
    if not math.isfinite(number):
        raise TabularDatasetError(
            f"Feature column {column} contains an infinite value at CSV row {row_number}."
        )
    return number


def _parse_target(value: Any, column: str, row_number: int, task_head: str) -> str | float:
    text = str(value or "").strip()
    if text.lower() in DEFAULT_MISSING_TOKENS:
        raise TabularDatasetError(
            f"Target column {column} is missing at CSV row {row_number}; targets are not imputed."
        )
    if task_head == "classification":
        return text
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise TabularDatasetError(
            f"Regression target column {column} contains a non-numeric value at CSV row "
            f"{row_number}: {value!r}."
        ) from exc
    if not math.isfinite(number):
        raise TabularDatasetError(
            f"Regression target column {column} contains an invalid value at CSV row {row_number}."
        )
    return number


def _parse_split(value: Any, column: str, row_number: int) -> str:
    text = str(value or "").strip().lower()
    normalized = _SPLIT_ALIASES.get(text)
    if normalized is None:
        raise TabularDatasetError(
            f"Split column {column} has invalid value at CSV row {row_number}: {value!r}. "
            "Use train, val, or test."
        )
    return normalized


def _provided_split_indices(records: Sequence[Mapping[str, Any]]) -> Dict[str, List[int]]:
    result = {name: [] for name in _SPLIT_NAMES}
    for index, record in enumerate(records):
        result[str(record["split"])].append(index)
    return result


def _random_split_indices(
    row_count: int, ratios: Tuple[float, float, float], seed: int
) -> Dict[str, List[int]]:
    rng = np.random.default_rng(seed)
    shuffled = np.arange(row_count, dtype=np.int64)
    rng.shuffle(shuffled)
    counts = _allocate_counts(row_count, ratios, tie_order=(0, 1, 2))
    return _indices_from_order(shuffled.tolist(), counts)


def _stratified_split_indices(
    targets: Sequence[str], ratios: Tuple[float, float, float], seed: int
) -> Dict[str, List[int]]:
    grouped: Dict[str, List[int]] = defaultdict(list)
    for index, target in enumerate(targets):
        grouped[str(target)].append(index)

    rng = np.random.default_rng(seed)
    result = {name: [] for name in _SPLIT_NAMES}
    for class_index, label in enumerate(sorted(grouped)):
        class_indices = np.asarray(grouped[label], dtype=np.int64)
        rng.shuffle(class_indices)
        # Alternating equal val/test ties prevents all two-sample classes from
        # collapsing into the same secondary split.
        secondary = (1, 2) if class_index % 2 == 0 else (2, 1)
        counts = _allocate_counts(
            len(class_indices),
            ratios,
            tie_order=(0, *secondary),
        )
        class_split = _indices_from_order(class_indices.tolist(), counts)
        for name in _SPLIT_NAMES:
            result[name].extend(class_split[name])

    for name in _SPLIT_NAMES:
        values = np.asarray(result[name], dtype=np.int64)
        rng.shuffle(values)
        result[name] = values.tolist()
    return result


def _allocate_counts(
    total: int,
    ratios: Tuple[float, float, float],
    tie_order: Tuple[int, int, int],
) -> List[int]:
    if total <= 0:
        return [0, 0, 0]
    raw = [total * ratio for ratio in ratios]
    counts = [int(math.floor(value)) for value in raw]
    tie_rank = {split_index: rank for rank, split_index in enumerate(tie_order)}
    remainder_order = sorted(
        range(3),
        key=lambda index: (-(raw[index] - counts[index]), tie_rank[index]),
    )
    for index in remainder_order[: total - sum(counts)]:
        counts[index] += 1

    active = [index for index, ratio in enumerate(ratios) if ratio > 0]
    minimums = [0, 0, 0]
    minimums[0] = 1
    if total >= len(active):
        for index in active:
            minimums[index] = 1
    for receiver in range(3):
        while counts[receiver] < minimums[receiver]:
            donors = [
                index for index in range(3) if counts[index] > minimums[index]
            ]
            if not donors:
                break
            donor = max(donors, key=lambda index: (counts[index] - minimums[index], -index))
            counts[donor] -= 1
            counts[receiver] += 1
    return counts


def _indices_from_order(order: List[int], counts: Sequence[int]) -> Dict[str, List[int]]:
    result: Dict[str, List[int]] = {}
    offset = 0
    for name, count in zip(_SPLIT_NAMES, counts):
        result[name] = order[offset : offset + count]
        offset += count
    return result


def _training_medians(
    records: Sequence[Mapping[str, Any]],
    train_indices: Sequence[int],
    feature_columns: Sequence[str],
) -> Dict[str, float]:
    medians: Dict[str, float] = {}
    for feature_index, column in enumerate(feature_columns):
        values = [
            float(records[row_index]["features"][feature_index])
            for row_index in train_indices
            if records[row_index]["features"][feature_index] is not None
        ]
        if not values:
            raise TabularDatasetError(
                f"Feature column {column} has no numeric value in the training split; "
                "a median cannot be fitted."
            )
        medians[column] = float(np.median(np.asarray(values, dtype=np.float64)))
    return medians


def _build_tensors(
    records: Sequence[Mapping[str, Any]],
    split_indices: Mapping[str, Sequence[int]],
    medians: Mapping[str, float],
    task_head: str,
    label_encoder: Mapping[str, int] | None,
) -> Dict[str, Dict[str, Any]]:
    feature_count = len(medians)
    median_values = list(medians.values())
    result: Dict[str, Dict[str, Any]] = {}
    for split_name in _SPLIT_NAMES:
        indices = list(split_indices[split_name])
        rows = []
        targets = []
        source_row_numbers = []
        for index in indices:
            record = records[index]
            rows.append(
                [
                    median_values[feature_index] if value is None else float(value)
                    for feature_index, value in enumerate(record["features"])
                ]
            )
            if task_head == "regression":
                targets.append(float(record["target"]))
            else:
                targets.append(int(label_encoder[str(record["target"])]))
            source_row_numbers.append(int(record["source_row_number"]))

        x = np.asarray(rows, dtype=np.float32)
        if not rows:
            x = np.empty((0, feature_count), dtype=np.float32)
        y_dtype = np.float32 if task_head == "regression" else np.int64
        result[split_name] = {
            "x": x,
            "y": np.asarray(targets, dtype=y_dtype),
            "row_indices": np.asarray(indices, dtype=np.int64),
            "source_row_numbers": np.asarray(source_row_numbers, dtype=np.int64),
        }
    return result


def _validate_ratios(
    train_ratio: float, val_ratio: float, test_ratio: float
) -> Tuple[float, float, float]:
    try:
        ratios = tuple(float(value) for value in (train_ratio, val_ratio, test_ratio))
    except (TypeError, ValueError) as exc:
        raise TabularDatasetError("Split ratios must be numeric values.") from exc
    if any(not math.isfinite(value) or value < 0 for value in ratios):
        raise TabularDatasetError("Split ratios must be finite, non-negative values.")
    if ratios[0] <= 0:
        raise TabularDatasetError("train_ratio must be greater than zero.")
    if not math.isclose(sum(ratios), 1.0, rel_tol=0.0, abs_tol=1e-8):
        raise TabularDatasetError("train_ratio, val_ratio, and test_ratio must add up to 1.0.")
    return ratios


def _validate_seed(seed: Any) -> int:
    if isinstance(seed, bool):
        raise TabularDatasetError("seed must be an integer.")
    try:
        normalized = int(seed)
    except (TypeError, ValueError) as exc:
        raise TabularDatasetError("seed must be an integer.") from exc
    if str(seed).strip() != str(normalized) and not isinstance(seed, int):
        raise TabularDatasetError("seed must be an integer.")
    if normalized < 0:
        raise TabularDatasetError("seed must be zero or greater.")
    return normalized


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _counts(values: Sequence[Any] | Any) -> Dict[Any, int]:
    result: Dict[Any, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
