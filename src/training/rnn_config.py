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
    _write_sequence_manifest(layout, csv_files, normalized, inspection)
    ProjectManager.save_project(project_id, project)
    return {
        "config": normalized,
        "validation": validation,
        "window": build_window_summary(normalized, inspection),
        "mismatches": find_config_mismatches(project),
        "inspection": inspection,
    }


def inspect_sequence_csv_files(paths: Iterable[Path]) -> Dict[str, Any]:
    files = []
    all_headers: List[str] = []
    header_sets = []
    row_count = 0
    sequence_counts: Counter[str] = Counter()
    split_counts: Counter[str] = Counter()
    samples: List[Dict[str, Any]] = []

    for path in paths:
        if not path.exists() or path.suffix.lower() != ".csv":
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            header_sets.append(headers)
            if not all_headers:
                all_headers = headers
            rows_in_file = 0
            for row in reader:
                row_count += 1
                rows_in_file += 1
                if len(samples) < 20:
                    samples.append({key: row.get(key, "") for key in headers})
                seq = str(row.get(_first_present(headers, ID_COLUMNS) or "") or "").strip()
                if seq:
                    sequence_counts[seq] += 1
                split = str(row.get("split") or "unknown").strip().lower() or "unknown"
                split_counts[split] += 1
            files.append({"name": path.name, "headers": headers, "rows": rows_in_file})

    headers_match = all(headers == all_headers for headers in header_sets) if header_sets else False
    sequence_col = _first_present(all_headers, ID_COLUMNS) or ""
    target_col = _first_present(all_headers, TARGET_COLUMNS) or ""
    time_col = _first_present(all_headers, TIME_COLUMNS) or ""
    feature_cols = [col for col in all_headers if col not in META_COLUMNS]
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
        "preview_rows": samples,
    }


def build_suggested_config(project: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    current = active_rnn_config(project)
    feature_columns = current.get("feature_columns") or inspection.get("feature_columns") or []
    config = {
        "feature_columns": feature_columns,
        "target_column": current.get("target_column") or inspection.get("target_column") or "",
        "sequence_column": current.get("sequence_column") or inspection.get("sequence_column") or "",
        "time_column": current.get("time_column") or inspection.get("time_column") or "",
        "sequence_length": int(current.get("sequence_length") or 16),
        "stride": int(current.get("stride") or 8),
        "horizon": int(current.get("horizon") or 1),
        "task_head": current.get("task_head") or "classification",
    }
    config["feature_config_hash"] = compute_feature_config_hash(config)
    return config


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
