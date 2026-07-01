from __future__ import annotations

import csv
import json
import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.project_layout import ProjectLayout


ID_COLUMNS = {"sequence_id", "session_id", "source_id", "video_id", "sample_id"}
TIME_COLUMNS = {"timestep", "time_step", "timestamp", "frame", "frame_idx", "index"}
TARGET_COLUMNS = {"label", "target", "target_value", "class", "y"}
META_COLUMNS = ID_COLUMNS | TIME_COLUMNS | TARGET_COLUMNS | {"split"}


def build_rnn_readiness_report(
    project: Dict[str, Any],
    sequence_length: int = 16,
    stride: int = 8,
    horizon: int = 1,
) -> Dict[str, Any]:
    layout = ProjectLayout.from_project(project)
    sequences_dir = layout.sequences_dir()
    manifest_path = layout.sequence_manifest_path()
    csv_files = sorted(sequences_dir.glob("*.csv")) if sequences_dir.exists() else []
    active_config = dict(project.get("rnn_config") or {})

    checks: List[Dict[str, Any]] = []
    manifest_summary = _empty_manifest_summary()
    csv_summary = _empty_csv_summary()

    _add_check(
        checks,
        "sequences_dir",
        "Sequences directory",
        "pass" if sequences_dir.exists() else "missing",
        "sequences directory is available." if sequences_dir.exists() else "Create project/sequences and add sequence_manifest.json or CSV feature files.",
    )

    if manifest_path.exists():
        manifest_summary, manifest_checks = _inspect_manifest(manifest_path, sequence_length)
        checks.extend(manifest_checks)
    else:
        _add_check(
            checks,
            "sequence_manifest",
            "sequence_manifest.json",
            "missing",
            "sequence_manifest.json is not connected yet.",
        )

    if csv_files:
        csv_summary, csv_checks = _inspect_csv_files(csv_files, sequence_length, active_config)
        checks.extend(csv_checks)
    else:
        _add_check(
            checks,
            "csv_feature_files",
            "CSV feature files",
            "missing",
            "No CSV feature sequence files found under project/sequences.",
        )

    has_parseable_source = manifest_summary["valid"] or csv_summary["valid"]
    has_train_val = _has_train_val(manifest_summary) or _has_train_val(csv_summary)
    has_labels = bool(manifest_summary.get("label_count") or csv_summary.get("label_count"))
    has_feature_dim = bool(csv_summary.get("feature_dim")) or bool(manifest_summary.get("feature_dim"))

    ready = bool(has_parseable_source and has_train_val and has_labels and has_feature_dim)
    status = "ready" if ready else "not_ready"

    return {
        "architecture": "rnn",
        "backend": "pytorch_lstm",
        "training_enabled": False,
        "status": status,
        "ready": ready,
        "sequence_length": sequence_length,
        "stride": stride,
        "horizon": horizon,
        "paths": {
            "sequences_dir": sequences_dir.as_posix(),
            "sequence_manifest": manifest_path.as_posix(),
            "csv_files": [path.as_posix() for path in csv_files],
        },
        "summary": {
            "manifest": manifest_summary,
            "csv": csv_summary,
            "source": "manifest" if manifest_summary["valid"] else "csv" if csv_summary["valid"] else "none",
            "active_config": active_config,
            "feature_config_hash": active_config.get("feature_config_hash") or _feature_config_hash(active_config),
            "ready_requirements": {
                "parseable_source": has_parseable_source,
                "train_val_split": has_train_val,
                "labels": has_labels,
                "feature_dim": has_feature_dim,
            },
        },
        "checks": checks,
        "message": (
            "RNN sequence data is ready for future training enablement."
            if ready
            else "RNN readiness is preview-only. Add sequence manifest or CSV feature files with train/val split and labels."
        ),
    }


def _inspect_manifest(path: Path, sequence_length: int) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []
    summary = _empty_manifest_summary()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _add_check(checks, "sequence_manifest_parse", "Manifest parse", "fail", f"Cannot parse sequence_manifest.json: {exc}")
        return summary, checks

    sequences = _extract_sequences(payload)
    summary["exists"] = True
    summary["sequence_count"] = len(sequences)
    summary["valid"] = len(sequences) > 0
    summary["split_counts"] = dict(Counter(str(seq.get("split", "unknown") or "unknown") for seq in sequences))
    summary["label_count"] = sum(1 for seq in sequences if _has_label(seq))
    lengths = [_sequence_length(seq) for seq in sequences]
    summary["min_length"] = min(lengths) if lengths else 0
    summary["max_length"] = max(lengths) if lengths else 0
    feature_dims = [_feature_dim(seq) for seq in sequences]
    feature_dims = [dim for dim in feature_dims if dim]
    summary["feature_dim"] = feature_dims[0] if feature_dims and len(set(feature_dims)) == 1 else 0

    _add_check(
        checks,
        "sequence_manifest_parse",
        "Manifest parse",
        "pass" if sequences else "fail",
        f"{len(sequences)} sequence records found." if sequences else "Manifest must contain a non-empty sequences list.",
    )
    _add_check(
        checks,
        "manifest_sequence_length",
        "Manifest sequence length",
        "pass" if lengths and min(lengths) >= sequence_length else "fail",
        f"Minimum sequence length is {summary['min_length']} for required {sequence_length}.",
    )
    _add_check(
        checks,
        "manifest_labels",
        "Manifest labels",
        "pass" if summary["label_count"] else "fail",
        f"{summary['label_count']} sequences include labels.",
    )
    _add_check(
        checks,
        "manifest_split",
        "Manifest train/val split",
        "pass" if _has_train_val(summary) else "fail",
        f"Split counts: {summary['split_counts']}.",
    )
    _add_check(
        checks,
        "manifest_feature_dim",
        "Manifest feature dim",
        "pass" if summary["feature_dim"] else "warning",
        "Consistent feature_dim found." if summary["feature_dim"] else "Manifest has no consistent feature_dim; CSV feature schema can satisfy this later.",
    )
    return summary, checks


def _inspect_csv_files(paths: Iterable[Path], sequence_length: int, active_config: Optional[Dict[str, Any]] = None) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    checks: List[Dict[str, Any]] = []
    summary = _empty_csv_summary()
    sequence_lengths: Dict[str, int] = defaultdict(int)
    split_by_sequence: Dict[str, str] = {}
    labels_by_sequence: Dict[str, Any] = {}
    feature_dims = set()
    row_count = 0
    files = list(paths)
    active_config = active_config or {}
    configured_features = [str(col).strip() for col in active_config.get("feature_columns") or [] if str(col).strip()]
    configured_target = str(active_config.get("target_column") or "").strip()
    configured_sequence = str(active_config.get("sequence_column") or "").strip()

    for path in files:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                if not headers:
                    _add_check(checks, f"csv_parse_{path.name}", f"CSV parse: {path.name}", "fail", "CSV has no header row.")
                    continue
                sequence_col = configured_sequence or _first_present(headers, ID_COLUMNS) or "sequence_id"
                target_col = configured_target or _first_present(headers, TARGET_COLUMNS)
                feature_cols = configured_features or [col for col in headers if col not in META_COLUMNS]
                if sequence_col not in headers:
                    _add_check(checks, f"csv_sequence_id_{path.name}", f"CSV sequence id: {path.name}", "fail", f"CSV must include sequence id column: {sequence_col}.")
                    continue
                missing_features = [col for col in feature_cols if col not in headers]
                if missing_features:
                    _add_check(checks, f"csv_features_{path.name}", f"CSV features: {path.name}", "fail", f"CSV is missing feature columns: {', '.join(missing_features)}.")
                    continue
                if not feature_cols:
                    _add_check(checks, f"csv_features_{path.name}", f"CSV features: {path.name}", "fail", "CSV must include at least one feature column.")
                    continue
                if not target_col or target_col not in headers:
                    _add_check(checks, f"csv_target_{path.name}", f"CSV target: {path.name}", "fail", f"CSV must include target column: {target_col or 'label/target'}.")
                    continue

                feature_dims.add(len(feature_cols))
                for row in reader:
                    row_count += 1
                    sequence_id = str(row.get(sequence_col) or "").strip()
                    if not sequence_id:
                        continue
                    sequence_lengths[sequence_id] += 1
                    split = str(row.get("split") or "unknown").strip() or "unknown"
                    split_by_sequence.setdefault(sequence_id, split)
                    if target_col and row.get(target_col) not in (None, ""):
                        labels_by_sequence.setdefault(sequence_id, row.get(target_col))
                _add_check(checks, f"csv_parse_{path.name}", f"CSV parse: {path.name}", "pass", f"{path.name} parsed.")
        except Exception as exc:
            _add_check(checks, f"csv_parse_{path.name}", f"CSV parse: {path.name}", "fail", f"Cannot parse CSV: {exc}")

    lengths = list(sequence_lengths.values())
    split_counts = Counter(split_by_sequence.values())
    consistent_dim = len(feature_dims) == 1
    summary.update(
        {
            "exists": bool(files),
            "file_count": len(files),
            "row_count": row_count,
            "sequence_count": len(sequence_lengths),
            "valid": bool(sequence_lengths and consistent_dim),
            "split_counts": dict(split_counts),
            "label_count": len(labels_by_sequence),
            "min_length": min(lengths) if lengths else 0,
            "max_length": max(lengths) if lengths else 0,
            "feature_dim": next(iter(feature_dims)) if consistent_dim and feature_dims else 0,
        }
    )

    _add_check(
        checks,
        "csv_sequence_length",
        "CSV sequence length",
        "pass" if lengths and min(lengths) >= sequence_length else "fail",
        f"Minimum CSV sequence length is {summary['min_length']} for required {sequence_length}.",
    )
    _add_check(
        checks,
        "csv_feature_dim",
        "CSV feature dim",
        "pass" if summary["feature_dim"] else "fail",
        "Consistent feature columns found." if summary["feature_dim"] else "Feature dimensions are missing or inconsistent.",
    )
    _add_check(
        checks,
        "csv_labels",
        "CSV labels",
        "pass" if summary["label_count"] else "fail",
        f"{summary['label_count']} sequences include labels.",
    )
    _add_check(
        checks,
        "csv_split",
        "CSV train/val split",
        "pass" if _has_train_val(summary) else "fail",
        f"Split counts: {summary['split_counts']}.",
    )
    return summary, checks


def _extract_sequences(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        sequences = payload.get("sequences") or payload.get("items") or payload.get("data") or []
        if isinstance(sequences, list):
            return [item for item in sequences if isinstance(item, dict)]
    return []


def _sequence_length(sequence: Dict[str, Any]) -> int:
    for key in ("frames", "timesteps", "features", "values", "steps"):
        value = sequence.get(key)
        if isinstance(value, list):
            return len(value)
    for key in ("length", "sequence_length", "window_size", "time_steps"):
        try:
            value = int(sequence.get(key) or 0)
            if value:
                return value
        except (TypeError, ValueError):
            continue
    return 0


def _feature_dim(sequence: Dict[str, Any]) -> int:
    for key in ("feature_dim", "input_dim"):
        try:
            value = int(sequence.get(key) or 0)
            if value:
                return value
        except (TypeError, ValueError):
            continue
    features = sequence.get("features")
    if isinstance(features, list) and features:
        first = features[0]
        if isinstance(first, dict):
            return len(first)
        if isinstance(first, list):
            return len(first)
    return 0


def _has_label(sequence: Dict[str, Any]) -> bool:
    return any(sequence.get(key) not in (None, "") for key in TARGET_COLUMNS)


def _has_train_val(summary: Dict[str, Any]) -> bool:
    splits = {str(key).lower(): value for key, value in (summary.get("split_counts") or {}).items()}
    return bool(splits.get("train") and splits.get("val"))


def _first_present(headers: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    lowered = {header.lower(): header for header in headers}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def _add_check(checks: List[Dict[str, Any]], key: str, label: str, status: str, message: str) -> None:
    checks.append({"key": key, "label": label, "status": status, "message": message, "action": _action_for_check(key, status)})


def _action_for_check(key: str, status: str) -> str:
    if status in {"pass", "warning"}:
        return ""
    if "csv_feature" in key or "csv_target" in key or "csv_sequence_id" in key:
        return "請到 RNN > 特徵與標籤確認欄位名稱，或重新匯入含正確 header 的 CSV。"
    if "csv_parse" in key:
        return "請確認 CSV 第一列是欄位名稱，例如 sequence_id,timestep,feature_1,target。"
    if "csv_split" in key:
        return "請在 CSV 加入 split 欄位，至少包含 train 與 val。"
    if "sequence_manifest" in key:
        return "請在 RNN > 序列資料集匯入 CSV 或 sequence_manifest.json。"
    return "請依照檢查訊息修正資料後重新檢查 readiness。"


def _feature_config_hash(config: Dict[str, Any]) -> str:
    payload = {
        "feature_columns": config.get("feature_columns") or [],
        "target_column": config.get("target_column") or "",
        "sequence_column": config.get("sequence_column") or "",
        "time_column": config.get("time_column") or "",
        "sequence_length": config.get("sequence_length") or 16,
        "stride": config.get("stride") or 8,
        "horizon": config.get("horizon") or 1,
        "task_head": config.get("task_head") or "classification",
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _empty_manifest_summary() -> Dict[str, Any]:
    return {
        "exists": False,
        "valid": False,
        "sequence_count": 0,
        "split_counts": {},
        "label_count": 0,
        "min_length": 0,
        "max_length": 0,
        "feature_dim": 0,
    }


def _empty_csv_summary() -> Dict[str, Any]:
    return {
        "exists": False,
        "valid": False,
        "file_count": 0,
        "row_count": 0,
        "sequence_count": 0,
        "split_counts": {},
        "label_count": 0,
        "min_length": 0,
        "max_length": 0,
        "feature_dim": 0,
    }
