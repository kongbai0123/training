from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.project_layout import ProjectLayout
from src.training.rnn_config import active_rnn_config, inspect_sequence_csv_files


def build_dataset_quality_report(project: Dict[str, Any]) -> Dict[str, Any]:
    architecture = _project_architecture(project)
    if architecture == "rnn":
        report = _build_rnn_quality_report(project)
    else:
        report = _build_cnn_quality_report(project)
    report["architecture"] = architecture
    report["project_id"] = project.get("project_id")
    report["task_type"] = project.get("task_type")
    report["health_score"] = _health_score(report.get("checks", []))
    return report


def _project_architecture(project: Dict[str, Any]) -> str:
    architecture = str(project.get("architecture") or project.get("mode") or "").lower()
    task_type = str(project.get("task_type") or "").lower()
    if architecture == "rnn" or task_type.startswith("sequence_") or "rnn" in task_type:
        return "rnn"
    return "cnn"


def _build_rnn_quality_report(project: Dict[str, Any]) -> Dict[str, Any]:
    layout = ProjectLayout.from_project(project)
    csv_files = sorted(layout.sequences_dir().glob("*.csv")) if layout.sequences_dir().exists() else []
    inspection = inspect_sequence_csv_files(csv_files) if csv_files else {
        "files": [],
        "headers": [],
        "row_count": 0,
        "sequence_count": 0,
        "column_profiles": {},
        "sequence_lengths": {},
        "split_counts": {},
    }
    config = active_rnn_config(project)
    target_column = str(config.get("target_column") or inspection.get("target_column") or "").strip()
    sequence_lengths = [int(value) for value in (inspection.get("sequence_lengths") or {}).values() if _is_positive_int(value)]
    sequence_anomalies = _sequence_length_anomalies(sequence_lengths)
    target_distribution = _target_distribution(csv_files, target_column) if target_column else {}
    split_counts = inspection.get("split_counts") or {}
    class_imbalance = _imbalance_summary(target_distribution) if target_distribution else {}
    missing_columns = _missing_column_summary(inspection.get("column_profiles") or {}, int(inspection.get("row_count") or 0))

    checks = [
        _check("csv_present", bool(csv_files), "CSV files are available.", "Import at least one RNN CSV file."),
        _check("headers_present", bool(inspection.get("headers")), "CSV header detected.", "CSV must include a header row."),
        _check("target_configured", bool(target_column), "Target column configured.", "Select a target column manually."),
        _check("features_configured", bool(config.get("feature_columns")), "Feature columns configured.", "Select one or more numeric feature columns."),
        _check("missing_values", not missing_columns.get("high_missing_columns"), "No high missing-value columns.", "Review high missing-value columns before training."),
        _check("sequence_length", not sequence_anomalies.get("severe"), "Sequence lengths look usable.", "Review short or highly variable sequence lengths."),
        _check("split_counts", bool(split_counts), "Split information detected or fallback can be applied.", "Add split column or rely on generated split fallback."),
    ]
    if class_imbalance:
        checks.append(_check(
            "target_balance",
            not class_imbalance.get("severe"),
            "Target distribution is not severely imbalanced.",
            "Review minority classes or collect more target samples.",
        ))

    return {
        "kind": "rnn_sequence",
        "summary": {
            "csv_files": [path.name for path in csv_files],
            "row_count": inspection.get("row_count", 0),
            "sequence_count": inspection.get("sequence_count", 0) or (1 if inspection.get("row_count") else 0),
            "feature_count": len(config.get("feature_columns") or []),
            "target_column": target_column,
            "task_head": config.get("task_head") or "classification",
            "split_counts": split_counts,
        },
        "missing_values": missing_columns,
        "distribution": {
            "target": target_distribution,
            "class_imbalance": class_imbalance,
            "split_counts": split_counts,
        },
        "sequence_lengths": {
            "min": min(sequence_lengths) if sequence_lengths else int(inspection.get("min_sequence_length") or 0),
            "max": max(sequence_lengths) if sequence_lengths else int(inspection.get("max_sequence_length") or 0),
            "count": len(sequence_lengths),
            "anomalies": sequence_anomalies,
        },
        "checks": checks,
    }


def _build_cnn_quality_report(project: Dict[str, Any]) -> Dict[str, Any]:
    images = project.get("images") or []
    labels = project.get("labels") or project.get("class_names") or []
    annotated = 0
    for item in images:
        if not isinstance(item, dict):
            continue
        if item.get("annotated") or item.get("labelme_json") or item.get("annotation_path"):
            annotated += 1
    image_count = len(images)
    class_counts = Counter()
    for item in images:
        if not isinstance(item, dict):
            continue
        for label in item.get("labels") or item.get("classes") or []:
            class_counts[str(label)] += 1
    split_counts = _project_split_counts(project)
    annotation_ratio = annotated / image_count if image_count else 0.0
    class_imbalance = _imbalance_summary(dict(class_counts))
    checks = [
        _check("images_present", image_count > 0, "Images are available.", "Import images before CNN training."),
        _check("annotations_present", annotated > 0, "Annotations detected.", "Create or import annotations."),
        _check("annotation_coverage", annotation_ratio >= 0.8 or image_count == 0, "Annotation coverage is acceptable.", "Review unannotated images."),
        _check("classes_present", bool(labels or class_counts), "Class names are available.", "Define class names before training."),
        _check("split_ready", bool(split_counts), "Dataset split is available.", "Create train / val / test split."),
    ]
    if class_counts:
        checks.append(_check("class_balance", not class_imbalance.get("severe"), "Classes are not severely imbalanced.", "Collect more samples for minority classes."))
    return {
        "kind": "cnn_vision",
        "summary": {
            "image_count": image_count,
            "annotated_count": annotated,
            "annotation_coverage": round(annotation_ratio, 4),
            "class_count": len(labels or class_counts),
            "split_counts": split_counts,
        },
        "missing_values": {
            "unannotated_images": max(0, image_count - annotated),
        },
        "distribution": {
            "classes": dict(class_counts),
            "class_imbalance": class_imbalance,
            "split_counts": split_counts,
        },
        "sequence_lengths": None,
        "checks": checks,
    }


def _missing_column_summary(profiles: Dict[str, Dict[str, Any]], row_count: int) -> Dict[str, Any]:
    rows = []
    high_missing = []
    for name, profile in profiles.items():
        missing = int(profile.get("missing") or 0)
        ratio = missing / max(row_count, 1) if row_count else 0.0
        row = {"column": name, "missing": missing, "missing_ratio": round(ratio, 4)}
        rows.append(row)
        if ratio >= 0.1:
            high_missing.append(row)
    rows.sort(key=lambda item: item["missing_ratio"], reverse=True)
    return {
        "columns": rows,
        "high_missing_columns": high_missing,
    }


def _target_distribution(paths: Iterable[Path], target_column: str, limit: int = 10000) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    rows = 0
    for path in paths:
        if rows >= limit:
            break
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if target_column not in (reader.fieldnames or []):
                continue
            for row in reader:
                value = str(row.get(target_column) or "").strip()
                if value:
                    counts[value] += 1
                rows += 1
                if rows >= limit:
                    break
    return dict(counts)


def _sequence_length_anomalies(lengths: List[int]) -> Dict[str, Any]:
    if not lengths:
        return {"severe": False, "short_sequences": 0, "high_variance": False}
    sorted_lengths = sorted(lengths)
    median = sorted_lengths[len(sorted_lengths) // 2]
    short = sum(1 for value in lengths if value < max(2, median * 0.25))
    high_variance = bool(max(lengths) > max(1, median) * 5)
    return {
        "severe": short > 0 or high_variance,
        "short_sequences": short,
        "high_variance": high_variance,
        "median": median,
    }


def _imbalance_summary(counts: Dict[str, Any]) -> Dict[str, Any]:
    numeric_counts = [int(value) for value in counts.values() if _is_positive_int(value)]
    if len(numeric_counts) < 2:
        return {"severe": False, "ratio": 1.0}
    min_count = min(numeric_counts)
    max_count = max(numeric_counts)
    ratio = max_count / max(min_count, 1)
    return {
        "severe": ratio >= 5.0,
        "ratio": round(ratio, 3),
        "minority_count": min_count,
        "majority_count": max_count,
    }


def _project_split_counts(project: Dict[str, Any]) -> Dict[str, int]:
    split = project.get("split") or project.get("dataset_split") or {}
    if isinstance(split, dict):
        result = {}
        for key in ("train", "val", "validation", "test"):
            value = split.get(key)
            if isinstance(value, list):
                result["val" if key == "validation" else key] = len(value)
            elif _is_positive_int(value):
                result["val" if key == "validation" else key] = int(value)
        return result
    return {}


def _check(name: str, passed: bool, ok: str, action: str) -> Dict[str, Any]:
    return {
        "name": name,
        "status": "pass" if passed else "warning",
        "message": ok if passed else action,
    }


def _health_score(checks: List[Dict[str, Any]]) -> int:
    if not checks:
        return 0
    passed = sum(1 for item in checks if item.get("status") == "pass")
    return int(round((passed / len(checks)) * 100))


def _is_positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False
