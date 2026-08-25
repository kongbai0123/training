from __future__ import annotations

import hashlib
import mimetypes
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from src.training.contracts import ARTIFACT_CONTRACT_VERSION, build_producer_metadata, utc_now_iso


_CONTENT_TYPES = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".log": "text/plain",
    ".onnx": "application/octet-stream",
    ".pt": "application/octet-stream",
    ".txt": "text/plain",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
}


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _CONTENT_TYPES:
        return _CONTENT_TYPES[suffix]
    guessed, _encoding = mimetypes.guess_type(path.name, strict=False)
    return guessed or "application/octet-stream"


def _artifact_entry(
    run_dir: Path,
    relative_path: str,
    artifact_type: str,
    role: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    path = (run_dir / relative_path).resolve()
    try:
        path.relative_to(run_dir.resolve())
    except ValueError:
        return None

    if not path.exists() or not path.is_file():
        return None

    entry: Dict[str, Any] = {
        "name": path.name,
        "type": artifact_type,
        "path": path.relative_to(run_dir.resolve()).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "content_type": _content_type(path),
    }
    if role:
        entry["role"] = role
    return entry


def _lineage_entry(value: Optional[Mapping[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} lineage must be a mapping")
    return deepcopy(dict(value))


def build_artifact_manifest(
    run_dir: Path,
    run_id: str,
    *,
    producer: Optional[Mapping[str, Any]] = None,
    dataset_lineage: Optional[Mapping[str, Any]] = None,
    model_lineage: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build an artifact contract v2 manifest.

    The original ``(run_dir, run_id)`` call remains supported.  Lineage is
    opt-in because legacy runs do not always have stable dataset/model IDs.
    """

    run_dir = run_dir.resolve()
    candidates = [
        ("weights/best.pt", "model_weight", "best_model"),
        ("weights/last.pt", "model_weight", "last_model"),
        ("weights/best.json", "xgboost_model", "best_model"),
        ("weights/last.json", "xgboost_model", "last_model"),
        ("weights/model_metadata.json", "model_metadata", "model_metadata"),
        ("feature_importance.json", "feature_importance", "diagnostics"),
        ("weights/best.onnx", "onnx_model", "export_model"),
        ("results.csv", "metrics_csv", "training_metrics"),
        ("metrics.json", "metrics_json", "metrics"),
        ("run_summary.json", "run_summary", "summary"),
        ("error.log", "error_log", "error"),
        ("backend.json", "backend_contract", "contract"),
        ("metric_schema.json", "metric_schema", "contract"),
        ("train_config.json", "training_config", "config"),
        ("dataset_snapshot.json", "dataset_snapshot", "dataset"),
        ("data.yaml", "dataset_config", "dataset"),
        ("preprocess/feature_schema.json", "feature_schema", "preprocess"),
        ("preprocess/label_encoder.json", "label_encoder", "preprocess"),
        ("preprocess/normalization_stats.json", "normalizer", "preprocess"),
        ("preprocess/imputation.json", "imputation", "preprocess"),
    ]

    artifacts: List[Dict[str, Any]] = []
    for relative_path, artifact_type, role in candidates:
        entry = _artifact_entry(run_dir, relative_path, artifact_type, role)
        if entry:
            artifacts.append(entry)

    manifest: Dict[str, Any] = {
        "contract_version": ARTIFACT_CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "producer": build_producer_metadata(ARTIFACT_CONTRACT_VERSION, producer),
        "artifacts": artifacts,
    }

    lineage: Dict[str, Any] = {}
    dataset = _lineage_entry(dataset_lineage, "dataset")
    model = _lineage_entry(model_lineage, "model")
    if dataset is not None:
        lineage["dataset"] = dataset
    if model is not None:
        lineage["model"] = model
    if lineage:
        manifest["lineage"] = lineage
    return manifest


def write_artifact_manifest(
    run_dir: Path,
    run_id: str,
    *,
    producer: Optional[Mapping[str, Any]] = None,
    dataset_lineage: Optional[Mapping[str, Any]] = None,
    model_lineage: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    import json

    manifest = build_artifact_manifest(
        run_dir,
        run_id,
        producer=producer,
        dataset_lineage=dataset_lineage,
        model_lineage=model_lineage,
    )
    path = Path(run_dir) / "artifact_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
