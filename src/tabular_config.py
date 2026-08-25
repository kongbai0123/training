from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List

from fastapi import UploadFile

from src.project_layout import ProjectLayout
from src.project_manager import ProjectManager
from src.security_utils import safe_filename


MAX_TABULAR_UPLOAD_BYTES = 512 * 1024 * 1024
TARGET_NAMES = ("target", "label", "class", "category", "outcome", "result", "y")
ID_NAMES = {"id", "row_id", "sample_id", "record_id", "uuid"}
SPLIT_NAMES = {"split", "subset", "partition", "fold"}
SPLIT_VALUE_ALIASES = {
    "train": "train",
    "training": "train",
    "val": "val",
    "valid": "val",
    "validation": "val",
    "dev": "val",
    "test": "test",
    "testing": "test",
}


def active_tabular_config(project: Dict[str, Any]) -> Dict[str, Any]:
    config = dict(project.get("tabular_config") or {})
    task_type = str(project.get("task_type") or "").lower()
    config.setdefault("source_file", "")
    config.setdefault("feature_columns", [])
    config.setdefault("target_column", "")
    config.setdefault("id_column", "")
    config.setdefault("split_column", "")
    config.setdefault("task_head", "regression" if "regression" in task_type else "classification")
    config.setdefault("seed", 42)
    config.setdefault("train_ratio", 0.70)
    config.setdefault("val_ratio", 0.15)
    config.setdefault("test_ratio", 0.15)
    config.setdefault("missing_strategy", "median")
    if not config.get("feature_config_hash"):
        config["feature_config_hash"] = compute_tabular_config_hash(config)
    return config


def compute_tabular_config_hash(config: Dict[str, Any]) -> str:
    seed_value = config.get("seed")
    payload = {
        "source_file": str(config.get("source_file") or ""),
        "feature_columns": _unique_names(config.get("feature_columns") or []),
        "target_column": str(config.get("target_column") or "").strip(),
        "id_column": str(config.get("id_column") or "").strip(),
        "split_column": str(config.get("split_column") or "").strip(),
        "task_head": str(config.get("task_head") or "classification").strip().lower(),
        "seed": int(seed_value if seed_value not in (None, "") else 42),
        "ratios": [
            _float_or_default(config.get("train_ratio"), 0.70),
            _float_or_default(config.get("val_ratio"), 0.15),
            _float_or_default(config.get("test_ratio"), 0.15),
        ],
        "missing_strategy": str(config.get("missing_strategy") or "median"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def import_tabular_csv(project: Dict[str, Any], upload: UploadFile) -> Dict[str, Any]:
    original_name = safe_filename(Path(upload.filename or "dataset.csv").name)
    if Path(original_name).suffix.lower() != ".csv":
        raise ValueError("Tabular datasets currently accept CSV files only.")

    layout = ProjectLayout.from_project(project)
    tables_dir = layout.tables_dir()
    tables_dir.mkdir(parents=True, exist_ok=True)
    target = _unique_path(tables_dir / original_name)
    copied = 0
    with target.open("wb") as handle:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            copied += len(chunk)
            if copied > MAX_TABULAR_UPLOAD_BYTES:
                handle.close()
                target.unlink(missing_ok=True)
                raise ValueError("CSV exceeds the 512 MB tabular import limit.")
            handle.write(chunk)

    try:
        inspection = inspect_tabular_csv(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if not inspection.get("headers") or not inspection.get("row_count"):
        target.unlink(missing_ok=True)
        raise ValueError("CSV must contain a header and at least one data row.")

    suggested = suggest_tabular_config(project, inspection, target)
    manifest = {
        "schema_version": "1.0",
        "source_file": target.relative_to(layout.project_dir).as_posix(),
        "source_sha256": _sha256(target),
        "size_bytes": target.stat().st_size,
        "imported_at": datetime.now().isoformat(),
        "inspection": {key: value for key, value in inspection.items() if key != "preview_rows"},
    }
    layout.tabular_manifest_path().write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "source_file": manifest["source_file"],
        "manifest": manifest,
        "inspection": inspection,
        "suggested_config": suggested,
    }


def inspect_tabular_csv(path: Path, *, preview_limit: int = 20) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists() or not path.is_file() or path.suffix.lower() != ".csv":
        raise ValueError("Tabular CSV file was not found.")
    row_count = 0
    preview_rows: List[Dict[str, str]] = []
    stats: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = [str(value or "").strip() for value in (reader.fieldnames or [])]
        if not headers or any(not header for header in headers) or len(set(headers)) != len(headers):
            raise ValueError("CSV headers must be non-empty and unique.")
        stats = {
            header: {
                "non_empty": 0,
                "numeric": 0,
                "missing": 0,
                "distinct": set(),
                "examples": [],
                "split_counts": {"train": 0, "val": 0, "test": 0},
                "invalid_split": 0,
            }
            for header in headers
        }
        for row in reader:
            row_count += 1
            if None in row:
                raise ValueError(f"CSV row {row_count + 1} has more values than the header.")
            if len(preview_rows) < preview_limit:
                preview_rows.append({header: str(row.get(header) or "") for header in headers})
            for header in headers:
                text = str(row.get(header) or "").strip()
                profile = stats[header]
                if not text or text.lower() in {"nan", "null", "none", "na", "n/a"}:
                    profile["missing"] += 1
                    continue
                profile["non_empty"] += 1
                try:
                    if math.isfinite(float(text)):
                        profile["numeric"] += 1
                except (TypeError, ValueError):
                    pass
                normalized_split = SPLIT_VALUE_ALIASES.get(text.lower())
                if normalized_split:
                    profile["split_counts"][normalized_split] += 1
                else:
                    profile["invalid_split"] += 1
                if len(profile["distinct"]) < 500:
                    profile["distinct"].add(text)
                if len(profile["examples"]) < 5:
                    profile["examples"].append(text)

    profiles: Dict[str, Dict[str, Any]] = {}
    for header, profile in stats.items():
        non_empty = int(profile["non_empty"])
        numeric_ratio = int(profile["numeric"]) / max(non_empty, 1)
        profiles[header] = {
            "non_empty": non_empty,
            "missing": int(profile["missing"]),
            "missing_ratio": round(int(profile["missing"]) / max(row_count, 1), 6),
            "numeric_ratio": round(numeric_ratio, 6),
            # Match the row-level training loader: every non-missing feature
            # value must be numeric. A heuristic threshold could otherwise
            # mark a CSV ready before the actual loader rejects it.
            "is_numeric": bool(
                non_empty
                and math.isclose(numeric_ratio, 1.0, rel_tol=0.0, abs_tol=1e-12)
            ),
            "distinct_count": len(profile["distinct"]),
            "examples": profile["examples"],
            "split_counts": dict(profile["split_counts"]),
            "invalid_split": int(profile["invalid_split"]),
        }
    return {
        "filename": path.name,
        "headers": headers,
        "row_count": row_count,
        "column_count": len(headers),
        "column_profiles": profiles,
        "preview_rows": preview_rows,
    }


def suggest_tabular_config(project: Dict[str, Any], inspection: Dict[str, Any], path: Path | None = None) -> Dict[str, Any]:
    headers = inspection.get("headers") or []
    profiles = inspection.get("column_profiles") or {}
    lowered = {str(header).lower(): header for header in headers}
    target = next((lowered[name] for name in TARGET_NAMES if name in lowered), "")
    if not target and headers:
        target = headers[-1]
    split_column = next((header for header in headers if str(header).lower() in SPLIT_NAMES), "")
    id_column = next((header for header in headers if str(header).lower() in ID_NAMES), "")
    features = [
        header for header in headers
        if header not in {target, split_column, id_column} and bool((profiles.get(header) or {}).get("is_numeric"))
    ]
    target_profile = profiles.get(target) or {}
    task_type = str(project.get("task_type") or "").lower()
    if task_type.startswith("tabular_"):
        task_head = "regression" if "regression" in task_type else "classification"
    else:
        target_is_numeric = bool(target_profile.get("is_numeric"))
        distinct = int(target_profile.get("distinct_count") or 0)
        rows = int(inspection.get("row_count") or 0)
        task_head = "regression" if target_is_numeric and distinct > max(20, int(rows * 0.05)) else "classification"
    source_file = ""
    if path:
        try:
            source_file = Path(path).resolve().relative_to(ProjectLayout.from_project(project).project_dir).as_posix()
        except ValueError:
            source_file = ""
    config = {
        "source_file": source_file,
        "feature_columns": features,
        "target_column": target,
        "id_column": id_column,
        "split_column": split_column,
        "task_head": task_head,
        "seed": 42,
        "train_ratio": 0.70,
        "val_ratio": 0.15,
        "test_ratio": 0.15,
        "missing_strategy": "median",
    }
    config["feature_config_hash"] = compute_tabular_config_hash(config)
    return config


def validate_tabular_config(config: Dict[str, Any], inspection: Dict[str, Any]) -> Dict[str, Any]:
    headers = set(inspection.get("headers") or [])
    profiles = inspection.get("column_profiles") or {}
    features = _unique_names(config.get("feature_columns") or [])
    target = str(config.get("target_column") or "").strip()
    id_column = str(config.get("id_column") or "").strip()
    split_column = str(config.get("split_column") or "").strip()
    errors: List[str] = []
    warnings: List[str] = []
    task_head = str(config.get("task_head") or "classification").strip().lower()
    if task_head not in {"classification", "regression"}:
        errors.append("Tabular task must be classification or regression.")
    if str(config.get("missing_strategy") or "median").strip().lower() != "median":
        errors.append("Tabular MVP currently supports median missing-value imputation only.")
    if not target or target not in headers:
        errors.append("Select a target column that exists in the CSV.")
    elif int((profiles.get(target) or {}).get("missing") or 0) > 0:
        errors.append("Target column contains missing values; targets are never imputed.")
    if target in headers and task_head == "regression" and not bool((profiles.get(target) or {}).get("is_numeric")):
        errors.append("Regression target column must contain finite numeric values only.")
    if target in headers and task_head == "classification" and int((profiles.get(target) or {}).get("distinct_count") or 0) < 2:
        errors.append("Classification target column must contain at least two distinct labels.")
    if not features:
        errors.append("Select at least one numeric feature column.")
    missing_features = [name for name in features if name not in headers]
    if missing_features:
        errors.append(f"Feature columns are missing from CSV: {', '.join(missing_features)}")
    non_numeric = [
        name for name in features
        if name in headers and not bool((inspection.get("column_profiles") or {}).get(name, {}).get("is_numeric"))
    ]
    if non_numeric:
        errors.append(f"Tabular MVP accepts numeric features only: {', '.join(non_numeric)}")
    if target in features:
        errors.append("Target column cannot also be a feature.")
    if id_column and id_column not in headers:
        errors.append("Configured ID column does not exist in CSV.")
    if id_column and id_column in features:
        errors.append("ID column cannot also be a feature.")
    if id_column and id_column == target:
        errors.append("ID column cannot also be the target column.")
    if id_column and id_column == split_column:
        errors.append("ID column cannot also be the split column.")
    if split_column and split_column not in headers:
        errors.append("Configured split column does not exist in CSV.")
    if split_column and split_column == target:
        errors.append("Split column cannot also be the target column.")
    if split_column in headers:
        split_profile = profiles.get(split_column) or {}
        invalid_split = int(split_profile.get("invalid_split") or 0) + int(split_profile.get("missing") or 0)
        if invalid_split:
            errors.append("Split column values must be train, val, or test (accepted aliases are training, validation, dev, and testing).")
        split_counts = split_profile.get("split_counts") or {}
        if int(split_counts.get("train") or 0) <= 0:
            errors.append("Provided split column must contain at least one training row.")
        if int(split_counts.get("val") or 0) <= 0:
            errors.append("Provided split column must contain at least one validation row.")
    ratios = [float(config.get(key) or 0) for key in ("train_ratio", "val_ratio", "test_ratio")]
    if not all(value >= 0 for value in ratios) or abs(sum(ratios) - 1.0) > 1e-6 or ratios[0] <= 0 or ratios[1] <= 0:
        errors.append("Train/validation/test ratios must be non-negative and sum to 1; train and validation must be positive.")
    row_count = int(inspection.get("row_count") or 0)
    if 0 < row_count < 6:
        errors.append("Tabular training requires at least 6 data rows so validation can be separated safely.")
    elif row_count < 30 and row_count > 0:
        warnings.append("Small datasets may not produce reliable validation metrics.")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def update_project_tabular_config(project_id: str, project: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    current = active_tabular_config(project)
    merged = {**current, **dict(payload or {})}
    merged["feature_columns"] = _unique_names(merged.get("feature_columns") or [])
    merged["target_column"] = str(merged.get("target_column") or "").strip()
    merged["id_column"] = str(merged.get("id_column") or "").strip()
    merged["split_column"] = str(merged.get("split_column") or "").strip()
    merged["task_head"] = str(merged.get("task_head") or "classification").strip().lower()
    if merged["task_head"] not in {"classification", "regression"}:
        raise ValueError("Tabular task_head must be classification or regression.")
    seed_value = merged.get("seed")
    merged["seed"] = int(seed_value if seed_value not in (None, "") else 42)
    for key, default in (("train_ratio", 0.70), ("val_ratio", 0.15), ("test_ratio", 0.15)):
        merged[key] = float(merged.get(key) if merged.get(key) is not None else default)
    source_path = resolve_tabular_source(project, merged)
    inspection = inspect_tabular_csv(source_path) if source_path else {"headers": [], "row_count": 0, "column_profiles": {}}
    validation = validate_tabular_config(merged, inspection)
    merged["feature_config_hash"] = compute_tabular_config_hash(merged)
    merged["updated_at"] = datetime.now().isoformat()
    project["tabular_config"] = merged
    project["task_type"] = f"tabular_{merged['task_head']}"
    project["training_config"] = {
        **ProjectManager._default_training_config(project["task_type"]),
        **(project.get("training_config") or {}),
        "backend": "xgboost_tabular",
        "architecture": "tabular",
        "model": "xgboost_regressor" if merged["task_head"] == "regression" else "xgboost_classifier",
        "task_head": merged["task_head"],
    }
    if not ProjectManager.save_project(project_id, project):
        raise RuntimeError("Unable to save tabular configuration.")
    return {"config": merged, "inspection": inspection, "validation": validation}


def resolve_tabular_source(project: Dict[str, Any], config: Dict[str, Any] | None = None) -> Path | None:
    layout = ProjectLayout.from_project(project)
    source = str((config or active_tabular_config(project)).get("source_file") or "").strip()
    if not source:
        candidates = sorted(layout.tables_dir().glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
        return candidates[0].resolve() if candidates else None
    candidate = (layout.project_dir / source).resolve()
    if layout.tables_dir().resolve() not in candidate.parents or candidate.suffix.lower() != ".csv":
        raise ValueError("Tabular source file must stay inside the project's dataset/tables directory.")
    if not candidate.exists() or not candidate.is_file():
        raise ValueError("Configured tabular source CSV does not exist.")
    return candidate


def get_tabular_workspace(project: Dict[str, Any]) -> Dict[str, Any]:
    config = active_tabular_config(project)
    source = resolve_tabular_source(project, config)
    inspection = inspect_tabular_csv(source) if source else {"headers": [], "row_count": 0, "column_profiles": {}, "preview_rows": []}
    recommendation = suggest_tabular_config(project, inspection, source) if source else config
    validation = validate_tabular_config(config, inspection)
    return {
        "config": config,
        "inspection": inspection,
        "recommendation": recommendation,
        "validation": validation,
        "ready": bool(source) and validation["valid"],
    }


def _unique_names(values: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        name = str(value or "").strip()
        if name and name not in seen:
            result.append(name)
            seen.add(name)
    return result


def _float_or_default(value: Any, default: float) -> float:
    return float(value if value not in (None, "") else default)


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
