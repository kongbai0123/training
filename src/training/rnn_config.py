from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import UploadFile

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.training.rnn_readiness import ID_COLUMNS, META_COLUMNS, TARGET_COLUMNS, TIME_COLUMNS


FEATURE_SPLIT_RE = re.compile(r"[,;，\n\r]+")
SEQUENCE_COLUMN_RE = re.compile(r"(sequence|seq|series|session|source|video|sample|machine|batch|asset|unit).*id|id.*(sequence|seq|series|session|source|video|sample|machine|batch|asset|unit)", re.I)
TIME_COLUMN_RE = re.compile(r"(^|[_\s-])(date|time|timestamp|timestep|time_step|frame|frame_idx|index)([_\s-]|$)", re.I)
TARGET_COLUMN_PRIORITY = {
    "label": 100,
    "class": 95,
    "category": 92,
    "target": 90,
    "targetvalue": 88,
    "y": 86,
    "fault": 84,
    "state": 82,
    "status": 80,
}
CLASSIFICATION_TARGET_NAMES = {"label", "class", "category", "fault", "state", "status"}


def parse_feature_columns(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = FEATURE_SPLIT_RE.split(str(value or ""))
    result: List[str] = []
    seen = set()
    for item in raw_items:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def active_rnn_config(project: Dict[str, Any]) -> Dict[str, Any]:
    config = dict(project.get("rnn_config") or {})
    config.setdefault("feature_columns", [])
    config.setdefault("target_column", "")
    config.setdefault("sequence_column", "")
    config.setdefault("time_column", "")
    config.setdefault("sequence_length", 16)
    config.setdefault("stride", 8)
    config.setdefault("horizon", 1)
    config.setdefault("task_head", "classification")
    if not config.get("feature_config_hash"):
        config["feature_config_hash"] = compute_feature_config_hash(config)
    return config


def compute_feature_config_hash(config: Dict[str, Any]) -> str:
    payload = {
        "feature_columns": parse_feature_columns(config.get("feature_columns")),
        "target_column": str(config.get("target_column") or "").strip(),
        "sequence_column": str(config.get("sequence_column") or "").strip(),
        "time_column": str(config.get("time_column") or "").strip(),
        "sequence_length": int(config.get("sequence_length") or 16),
        "stride": int(config.get("stride") or 8),
        "horizon": int(config.get("horizon") or 1),
        "task_head": str(config.get("task_head") or "classification").strip().lower(),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def import_sequence_dataset(project: Dict[str, Any], upload: UploadFile) -> Dict[str, Any]:
    layout = ProjectLayout.from_project(project)
    sequences_dir = layout.sequences_dir()
    raw_dir = sequences_dir / "raw"
    sequences_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(upload.filename or "sequence.csv").name
    suffix = Path(original_name).suffix.lower()
    imported: List[Path] = []

    if suffix == ".csv":
        target = _unique_path(sequences_dir / original_name)
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        imported.append(target)
    elif suffix == ".zip":
        package_path = _unique_path(raw_dir / original_name)
        with package_path.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        imported.extend(_safe_extract_csv_zip(package_path, sequences_dir))
    else:
        raise ValueError("Only .csv or .zip containing CSV files can be imported for RNN sequence datasets.")

    if not imported:
        raise ValueError("No CSV files were imported. Please upload a CSV or a ZIP containing CSV files.")

    inspection = inspect_sequence_csv_files(imported)
    suggested = build_suggested_config(project, inspection)
    _write_sequence_manifest(layout, imported, suggested, inspection)
    return {
        "imported_files": [path.relative_to(layout.project_dir).as_posix() for path in imported],
        "inspection": inspection,
        "suggested_config": suggested,
        "manifest_path": layout.sequence_manifest_path().relative_to(layout.project_dir).as_posix(),
    }


def update_project_rnn_config(project_id: str, project: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    layout = ProjectLayout.from_project(project)
    csv_files = sorted(layout.sequences_dir().glob("*.csv"))
    inspection = inspect_sequence_csv_files(csv_files) if csv_files else {"headers": [], "files": []}

    normalized = {
        "feature_columns": parse_feature_columns(config.get("feature_columns")),
        "target_column": str(config.get("target_column") or "").strip(),
        "sequence_column": str(config.get("sequence_column") or "").strip(),
        "time_column": str(config.get("time_column") or "").strip(),
        "sequence_length": max(1, int(config.get("sequence_length") or 16)),
        "stride": max(1, int(config.get("stride") or 8)),
        "horizon": max(1, int(config.get("horizon") or 1)),
        "task_head": str(config.get("task_head") or "classification").strip().lower(),
    }
    validation = validate_rnn_config(normalized, inspection)
    normalized["feature_config_hash"] = compute_feature_config_hash(normalized)
    normalized["updated_at"] = datetime.now().isoformat()
    project["rnn_config"] = normalized
    if normalized["task_head"] in {"classification", "regression"}:
        project["task_type"] = f"sequence_{normalized['task_head']}"
    _write_sequence_manifest(layout, csv_files, normalized, inspection)
    ProjectManager.save_project(project_id, project)
    return {
        "config": normalized,
        "validation": validation,
        "window": build_window_summary(normalized, inspection),
        "mismatches": find_config_mismatches(project),
        "inspection": inspection,
        "recommendation": build_suggested_config(project, inspection),
    }


def inspect_sequence_csv_files(paths: Iterable[Path]) -> Dict[str, Any]:
    files = []
    all_headers: List[str] = []
    header_sets = []
    row_count = 0
    sequence_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    samples: List[Dict[str, Any]] = []
    column_stats: Dict[str, Dict[str, Any]] = {}

    for path in paths:
        if not path.exists() or path.suffix.lower() != ".csv":
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            header_sets.append(headers)
            if not all_headers:
                all_headers = headers
            for header in headers:
                column_stats.setdefault(header, {"non_empty": 0, "numeric": 0, "distinct": set(), "examples": []})
            rows_in_file = 0
            for row in reader:
                row_count += 1
                rows_in_file += 1
                if len(samples) < 20:
                    samples.append({key: row.get(key, "") for key in headers})
                for header in headers:
                    value = row.get(header)
                    text = str(value or "").strip()
                    if not text:
                        continue
                    stats = column_stats.setdefault(header, {"non_empty": 0, "numeric": 0, "distinct": set(), "examples": []})
                    stats["non_empty"] += 1
                    if _is_float_like(text):
                        stats["numeric"] += 1
                    if len(stats["distinct"]) < 200:
                        stats["distinct"].add(text)
                    if len(stats["examples"]) < 5:
                        stats["examples"].append(text)
                seq = str(row.get(_first_present(headers, ID_COLUMNS) or "") or "").strip()
                if seq:
                    sequence_counts[seq] += 1
                split = str(row.get("split") or "unknown").strip().lower() or "unknown"
                split_counts[split] += 1
            files.append({"name": path.name, "headers": headers, "rows": rows_in_file})

    headers_match = all(headers == all_headers for headers in header_sets) if header_sets else False
    column_profiles = _build_column_profiles(column_stats, all_headers, row_count)
    suggested = infer_rnn_config_from_inspection(all_headers, column_profiles, row_count)
    sequence_col = suggested.get("sequence_column") or ""
    target_col = suggested.get("target_column") or ""
    time_col = suggested.get("time_column") or ""
    feature_cols = suggested.get("feature_columns") or []
    lengths = list(sequence_counts.values())
    return {
        "files": files,
        "headers": all_headers,
        "headers_match": headers_match,
        "row_count": row_count,
        "sequence_count": len(sequence_counts),
        "min_sequence_length": min(lengths) if lengths else 0,
        "max_sequence_length": max(lengths) if lengths else 0,
        "sequence_lengths": dict(sequence_counts),
        "split_counts": dict(split_counts),
        "sequence_column": sequence_col,
        "target_column": target_col,
        "time_column": time_col,
        "feature_columns": feature_cols,
        "feature_dim": len(feature_cols),
        "column_profiles": column_profiles,
        "suggested_config": suggested,
        "preview_rows": samples,
    }


def build_suggested_config(project: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    current = active_rnn_config(project)
    inferred = dict(inspection.get("suggested_config") or {})
    feature_columns = inferred.get("feature_columns") or inspection.get("feature_columns") or []
    config = {
        "feature_columns": feature_columns,
        "target_column": inferred.get("target_column") or inspection.get("target_column") or "",
        "sequence_column": inferred.get("sequence_column") or inspection.get("sequence_column") or "",
        "time_column": inferred.get("time_column") or inspection.get("time_column") or "",
        "sequence_length": int(current.get("sequence_length") or 16),
        "stride": int(current.get("stride") or 8),
        "horizon": int(current.get("horizon") or 1),
        "task_head": inferred.get("task_head") or current.get("task_head") or "classification",
        "recommendation_confidence": inferred.get("recommendation_confidence") or "unknown",
        "recommendation_reason": inferred.get("recommendation_reason") or "",
    }
    config["feature_config_hash"] = compute_feature_config_hash(config)
    return config


def build_schema_wizard(project: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    """Build role-oriented schema guidance for generic RNN CSV datasets."""
    config = active_rnn_config(project)
    recommendation = build_suggested_config(project, inspection)
    headers = inspection.get("headers") or []
    profiles = inspection.get("column_profiles") or {}
    selected_features = set(parse_feature_columns(config.get("feature_columns")))
    selected_target = str(config.get("target_column") or "").strip()
    selected_sequence = str(config.get("sequence_column") or "").strip()
    selected_time = str(config.get("time_column") or "").strip()
    recommended_features = set(parse_feature_columns(recommendation.get("feature_columns")))

    columns: List[Dict[str, Any]] = []
    for name in headers:
        profile = profiles.get(name) or {}
        current_role = "ignored"
        if name == selected_target:
            current_role = "target"
        elif selected_sequence and name == selected_sequence:
            current_role = "sequence_id"
        elif selected_time and name == selected_time:
            current_role = "time"
        elif name in selected_features:
            current_role = "feature"

        recommended_role = _schema_wizard_recommended_role(name, recommendation, profile)
        missing = int(profile.get("missing") or 0)
        row_count = max(0, int(inspection.get("row_count") or 0))
        warnings: List[str] = []
        if missing and row_count:
            missing_ratio = missing / max(row_count, 1)
            if missing_ratio >= 0.1:
                warnings.append("missing_values")
        if recommended_role == "feature" and not bool(profile.get("is_numeric")):
            warnings.append("non_numeric_feature")
        if recommended_role == "target" and recommendation.get("recommendation_confidence") == "needs_user":
            warnings.append("target_needs_manual_selection")

        columns.append({
            "name": name,
            "current_role": current_role,
            "recommended_role": recommended_role,
            "role_hint": profile.get("role_hint") or "feature",
            "is_numeric": bool(profile.get("is_numeric")),
            "numeric_ratio": float(profile.get("numeric_ratio") or 0.0),
            "missing": missing,
            "missing_ratio": round((missing / max(row_count, 1)) if row_count else 0.0, 4),
            "distinct_count": int(profile.get("distinct_count") or 0),
            "examples": profile.get("examples") or [],
            "warnings": warnings,
            "selectable_roles": _schema_wizard_selectable_roles(profile),
        })

    target_status = "manual_required" if not recommendation.get("target_column") else "suggested"
    if selected_target:
        target_status = "configured"
    return {
        "schema_version": "1.0",
        "project_id": project.get("project_id"),
        "task_type": project.get("task_type"),
        "row_count": inspection.get("row_count", 0),
        "sequence_count": inspection.get("sequence_count", 0),
        "headers_match": inspection.get("headers_match", True),
        "columns": columns,
        "task_options": [
            {
                "value": "classification",
                "label": "Classification",
                "recommended": recommendation.get("task_head") == "classification",
                "hint": "Use for discrete labels, class states, fault categories, or pass/fail targets.",
            },
            {
                "value": "regression",
                "label": "Regression",
                "recommended": recommendation.get("task_head") == "regression",
                "hint": "Use for continuous numeric targets such as temperature, pressure, load, or demand.",
            },
        ],
        "roles": {
            "time_column": selected_time,
            "sequence_column": selected_sequence,
            "feature_columns": list(selected_features),
            "target_column": selected_target,
            "task_head": config.get("task_head") or recommendation.get("task_head") or "classification",
        },
        "recommendation": recommendation,
        "recommended_feature_columns": list(recommended_features),
        "target_status": target_status,
        "steps": [
            {"id": "task", "label": "Task type", "status": "ready" if recommendation.get("task_head") else "needs_input"},
            {"id": "target", "label": "Target column", "status": target_status},
            {"id": "features", "label": "Feature columns", "status": "ready" if recommended_features or selected_features else "needs_input"},
            {"id": "sequence", "label": "Time / sequence", "status": "ready"},
        ],
    }


def _schema_wizard_recommended_role(name: str, recommendation: Dict[str, Any], profile: Dict[str, Any]) -> str:
    if name == recommendation.get("target_column"):
        return "target"
    if name == recommendation.get("sequence_column"):
        return "sequence_id"
    if name == recommendation.get("time_column"):
        return "time"
    if name in set(parse_feature_columns(recommendation.get("feature_columns"))):
        return "feature"
    hint = str(profile.get("role_hint") or "").lower()
    if hint == "split":
        return "split"
    return "ignored"


def _schema_wizard_selectable_roles(profile: Dict[str, Any]) -> List[str]:
    roles = ["ignored", "target", "time", "sequence_id"]
    if bool(profile.get("is_numeric")):
        roles.insert(1, "feature")
    else:
        roles.append("feature")
    return roles


def infer_rnn_config_from_inspection(headers: List[str], column_profiles: Dict[str, Dict[str, Any]], row_count: int = 0) -> Dict[str, Any]:
    sequence_column = _infer_sequence_column(headers)
    time_column = _infer_time_column(headers, column_profiles, sequence_column)
    target = _infer_target_column(headers, column_profiles, sequence_column, time_column, row_count)
    target_column = target.get("name", "")
    reserved = {value for value in (sequence_column, time_column, target_column, "split") if value}
    feature_columns = [
        name for name in headers
        if name not in reserved and _is_numeric_profile(column_profiles.get(name, {}))
    ]
    return {
        "feature_columns": feature_columns,
        "target_column": target_column,
        "sequence_column": sequence_column,
        "time_column": time_column,
        "sequence_length": 16,
        "stride": 8,
        "horizon": 1,
        "task_head": target.get("task_head") or "regression",
        "recommendation_confidence": target.get("confidence") or "needs_user",
        "recommendation_reason": target.get("reason") or (
            "No strong target column was detected. Select the prediction target manually."
            if not target_column
            else "Target column inferred from CSV schema."
        ),
    }


def validate_rnn_config(config: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    headers = inspection.get("headers") or []
    header_set = set(headers)
    feature_columns = parse_feature_columns(config.get("feature_columns"))
    missing_features = [name for name in feature_columns if name not in header_set]
    target_column = str(config.get("target_column") or "").strip()
    sequence_column = str(config.get("sequence_column") or "").strip()
    time_column = str(config.get("time_column") or "").strip()
    sequence_length = max(1, int(config.get("sequence_length") or 16))
    stride = max(1, int(config.get("stride") or 8))
    horizon = max(1, int(config.get("horizon") or 1))
    window = build_window_summary(config, inspection)
    warnings = []
    errors = []
    if not feature_columns:
        errors.append("請至少選擇一個 feature column。")
    if missing_features:
        errors.append(f"CSV 中找不到 feature columns: {', '.join(missing_features)}")
    if not target_column or target_column not in header_set:
        errors.append("請選擇存在於 CSV header 的 target column。")
    if not sequence_column or sequence_column not in header_set:
        errors.append("請選擇存在於 CSV header 的 sequence id column。")
    if time_column and time_column not in header_set:
        warnings.append("time column 不存在，訓練時會使用 CSV 原始順序。")
    if not inspection.get("headers_match", True):
        warnings.append("多個 CSV 的 header 不完全一致，建議先統一欄位。")
    if stride > sequence_length:
        warnings.append("stride 大於 sequence_length，可能會略過大量可用片段。")
    if horizon > sequence_length:
        warnings.append("horizon 大於 sequence_length，請確認是否符合預測目標。")
    if window["status"] == "error":
        errors.extend(window["errors"])
    elif window["warnings"]:
        warnings.extend(window["warnings"])
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "window": window,
        "feature_status": [
            {"name": name, "exists": name in header_set, "role": "feature"} for name in feature_columns
        ],
    }


def build_window_summary(config: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    sequence_length = max(1, int(config.get("sequence_length") or 16))
    stride = max(1, int(config.get("stride") or 8))
    horizon = max(1, int(config.get("horizon") or 1))
    raw_lengths = inspection.get("sequence_lengths") or {}
    length_values: List[int] = []
    if isinstance(raw_lengths, dict):
        for value in raw_lengths.values():
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                length_values.append(parsed)

    min_length = min(length_values) if length_values else int(inspection.get("min_sequence_length") or 0)
    max_length = max(length_values) if length_values else int(inspection.get("max_sequence_length") or 0)
    estimated_windows = 0
    for length in length_values:
        usable_length = length - horizon + 1
        if usable_length >= sequence_length:
            estimated_windows += ((usable_length - sequence_length) // stride) + 1

    errors: List[str] = []
    warnings: List[str] = []
    if length_values and estimated_windows <= 0:
        errors.append("目前 sequence_length / horizon 無法從已匯入 CSV 切出訓練片段。")
    elif not length_values:
        warnings.append("尚無序列長度統計；請先匯入 CSV 後再驗證切片設定。")

    status = "error" if errors else "warning" if warnings else "ok"
    return {
        "status": status,
        "sequence_length": sequence_length,
        "stride": stride,
        "horizon": horizon,
        "sequence_count": len(length_values) or int(inspection.get("sequence_count") or 0),
        "min_sequence_length": min_length,
        "max_sequence_length": max_length,
        "estimated_windows": estimated_windows,
        "errors": errors,
        "warnings": warnings,
    }


def validate_rnn_config(config: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    headers = inspection.get("headers") or []
    header_set = set(headers)
    feature_columns = parse_feature_columns(config.get("feature_columns"))
    missing_features = [name for name in feature_columns if name not in header_set]
    target_column = str(config.get("target_column") or "").strip()
    sequence_column = str(config.get("sequence_column") or "").strip()
    time_column = str(config.get("time_column") or "").strip()
    sequence_length = max(1, int(config.get("sequence_length") or 16))
    stride = max(1, int(config.get("stride") or 8))
    horizon = max(1, int(config.get("horizon") or 1))
    window = build_window_summary(config, inspection)
    warnings = []
    errors = []

    if not headers:
        errors.append("CSV header was not detected. Import a CSV file with a header row first.")
    if not feature_columns:
        errors.append("Select at least one feature column from the CSV header.")
    if missing_features:
        errors.append(f"CSV is missing configured feature columns: {', '.join(missing_features)}")
    if not target_column or target_column not in header_set:
        errors.append("Select a target column that exists in the CSV header.")
    if sequence_column and sequence_column not in header_set:
        errors.append("Select a sequence id column that exists in the CSV header, or leave it empty for one continuous sequence.")
    if time_column and time_column not in header_set:
        warnings.append("The configured time column was not found; sequence rows will use CSV row order.")
    if not inspection.get("headers_match", True):
        warnings.append("Imported CSV files have different headers; use one consistent schema before training.")
    if stride > sequence_length:
        warnings.append("stride is greater than sequence_length; this can skip many possible training windows.")
    if horizon > sequence_length:
        warnings.append("horizon is greater than sequence_length; verify the expected prediction distance.")
    if window["status"] == "error":
        errors.extend(window["errors"])
    elif window["warnings"]:
        warnings.extend(window["warnings"])
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "window": window,
        "feature_status": [
            {"name": name, "exists": name in header_set, "role": "feature"} for name in feature_columns
        ],
    }


def build_window_summary(config: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    sequence_length = max(1, int(config.get("sequence_length") or 16))
    stride = max(1, int(config.get("stride") or 8))
    horizon = max(1, int(config.get("horizon") or 1))
    raw_lengths = inspection.get("sequence_lengths") or {}
    length_values: List[int] = []
    if isinstance(raw_lengths, dict):
        for value in raw_lengths.values():
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                length_values.append(parsed)

    min_length = min(length_values) if length_values else int(inspection.get("min_sequence_length") or 0)
    max_length = max(length_values) if length_values else int(inspection.get("max_sequence_length") or 0)
    estimated_windows = 0
    for length in length_values:
        usable_length = length - horizon + 1
        if usable_length >= sequence_length:
            estimated_windows += ((usable_length - sequence_length) // stride) + 1

    errors: List[str] = []
    warnings: List[str] = []
    if length_values and estimated_windows <= 0:
        errors.append("The current sequence_length / horizon settings produce zero training windows for the imported CSV data.")
    elif not length_values:
        row_count = int(inspection.get("row_count") or 0)
        usable_length = row_count - horizon + 1
        if row_count and usable_length >= sequence_length:
            estimated_windows = ((usable_length - sequence_length) // stride) + 1
            length_values = [row_count]
            min_length = row_count
            max_length = row_count
        elif row_count:
            errors.append("The current sequence_length / horizon settings produce zero training windows for the single continuous CSV sequence.")
        else:
            warnings.append("No sequence lengths were detected. Import CSV data before training.")

    status = "error" if errors else "warning" if warnings else "ok"
    return {
        "status": status,
        "sequence_length": sequence_length,
        "stride": stride,
        "horizon": horizon,
        "sequence_count": len(length_values) or int(inspection.get("sequence_count") or 0),
        "min_sequence_length": min_length,
        "max_sequence_length": max_length,
        "estimated_windows": estimated_windows,
        "errors": errors,
        "warnings": warnings,
    }


def find_config_mismatches(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    current_hash = active_rnn_config(project).get("feature_config_hash")
    mismatches = []
    for run in project.get("training_runs", []) or []:
        architecture = str(run.get("architecture") or "").lower()
        backend = str(run.get("backend") or "").lower()
        if architecture != "rnn" and backend != "pytorch_lstm":
            continue
        run_hash = run.get("feature_config_hash")
        if run_hash and current_hash and run_hash != current_hash:
            mismatches.append({
                "run_id": run.get("run_id"),
                "run_hash": run_hash,
                "current_hash": current_hash,
                "status": "config_mismatch",
            })
    return mismatches


def _write_sequence_manifest(layout: ProjectLayout, csv_files: Iterable[Path], config: Dict[str, Any], inspection: Dict[str, Any]) -> None:
    manifest = {
        "schema_version": "1.0",
        "created_at": datetime.now().isoformat(),
        "source": "csv",
        "csv_files": [path.relative_to(layout.project_dir).as_posix() for path in csv_files if path.exists()],
        "feature_config": config,
        "inspection": {
            "headers": inspection.get("headers", []),
            "row_count": inspection.get("row_count", 0),
            "sequence_count": inspection.get("sequence_count", 0),
            "min_sequence_length": inspection.get("min_sequence_length", 0),
            "max_sequence_length": inspection.get("max_sequence_length", 0),
            "split_counts": inspection.get("split_counts", {}),
            "feature_dim": len(config.get("feature_columns") or []),
        },
    }
    layout.sequence_manifest_path().parent.mkdir(parents=True, exist_ok=True)
    layout.sequence_manifest_path().write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_extract_csv_zip(zip_path: Path, target_dir: Path) -> List[Path]:
    extracted: List[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            name = Path(member.filename).name
            if not name or Path(name).suffix.lower() != ".csv":
                continue
            target = _unique_path(target_dir / name)
            resolved = target.resolve()
            if target_dir.resolve() not in resolved.parents and resolved != target_dir.resolve():
                raise ValueError("Unsafe ZIP path detected.")
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    return extracted


def _build_column_profiles(stats_by_column: Dict[str, Dict[str, Any]], headers: List[str], row_count: int) -> Dict[str, Dict[str, Any]]:
    profiles: Dict[str, Dict[str, Any]] = {}
    for header in headers:
        stats = stats_by_column.get(header) or {"non_empty": 0, "numeric": 0, "distinct": set(), "examples": []}
        distinct_values = stats.get("distinct") or set()
        non_empty = int(stats.get("non_empty") or 0)
        numeric = int(stats.get("numeric") or 0)
        numeric_ratio = (numeric / non_empty) if non_empty else 0.0
        profiles[header] = {
            "name": header,
            "non_empty": non_empty,
            "missing": max(0, row_count - non_empty),
            "numeric_count": numeric,
            "numeric_ratio": round(numeric_ratio, 4),
            "is_numeric": bool(non_empty and numeric_ratio >= 0.95),
            "distinct_count": len(distinct_values),
            "examples": list(stats.get("examples") or []),
            "role_hint": _role_hint(header),
        }
    return profiles


def _infer_sequence_column(headers: List[str]) -> str:
    exact = _first_present(headers, ID_COLUMNS)
    if exact:
        return exact
    return next((name for name in headers if SEQUENCE_COLUMN_RE.search(name)), "")


def _infer_time_column(headers: List[str], profiles: Dict[str, Dict[str, Any]], sequence_column: str = "") -> str:
    exact = _first_present(headers, TIME_COLUMNS)
    if exact:
        return exact
    for name in headers:
        if name == sequence_column:
            continue
        if TIME_COLUMN_RE.search(name):
            return name
    return ""


def _infer_target_column(
    headers: List[str],
    profiles: Dict[str, Dict[str, Any]],
    sequence_column: str = "",
    time_column: str = "",
    row_count: int = 0,
) -> Dict[str, Any]:
    reserved = {value for value in (sequence_column, time_column, "split") if value}
    candidates: List[Dict[str, Any]] = []
    for name in headers:
        if name in reserved:
            continue
        normalized = _normalized_column_name(name)
        priority = TARGET_COLUMN_PRIORITY.get(normalized)
        if priority is None:
            continue
        profile = profiles.get(name, {})
        candidates.append({"name": name, "priority": priority, "profile": profile, "normalized": normalized})

    if not candidates:
        return {
            "name": "",
            "task_head": "regression" if any(_is_numeric_profile(profiles.get(name, {})) for name in headers if name not in reserved) else "classification",
            "confidence": "needs_user",
            "reason": "No explicit label/target/class/y column was found.",
        }

    selected = sorted(candidates, key=lambda item: (-item["priority"], headers.index(item["name"])))[0]
    profile = selected["profile"]
    normalized = selected["normalized"]
    task_head = _target_task_head(normalized, profile, row_count)
    confidence = "strong" if selected["priority"] >= 90 else "medium"
    return {
        "name": selected["name"],
        "task_head": task_head,
        "confidence": confidence,
        "reason": f"Column '{selected['name']}' matched the common target role '{normalized}'.",
    }


def _target_task_head(normalized_name: str, profile: Dict[str, Any], row_count: int) -> str:
    if normalized_name in CLASSIFICATION_TARGET_NAMES:
        return "classification"
    if not _is_numeric_profile(profile):
        return "classification"
    distinct = int(profile.get("distinct_count") or 0)
    non_empty = int(profile.get("non_empty") or row_count or 0)
    if normalized_name in {"y"} and distinct and distinct <= 20 and (not non_empty or distinct / max(non_empty, 1) <= 0.2):
        return "classification"
    return "regression"


def _role_hint(name: str) -> str:
    normalized = _normalized_column_name(name)
    if normalized in TARGET_COLUMN_PRIORITY:
        return "target"
    if normalized in {_normalized_column_name(value) for value in ID_COLUMNS} or SEQUENCE_COLUMN_RE.search(name):
        return "sequence"
    if normalized in {_normalized_column_name(value) for value in TIME_COLUMNS} or TIME_COLUMN_RE.search(name):
        return "time"
    if normalized == "split":
        return "split"
    return "feature"


def _normalized_column_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name or "").strip().lower())


def _is_numeric_profile(profile: Dict[str, Any]) -> bool:
    return bool(profile.get("is_numeric"))


def _is_float_like(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for index in range(1, 10000):
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError(f"Unable to allocate file name for {path.name}")


def _first_present(headers: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lowered = {header.lower(): header for header in headers}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None
