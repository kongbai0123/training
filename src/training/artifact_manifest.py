from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.training.contracts import CONTRACT_VERSION, utc_now_iso


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
    }
    if role:
        entry["role"] = role
    return entry


def build_artifact_manifest(run_dir: Path, run_id: str) -> Dict[str, Any]:
    run_dir = run_dir.resolve()
    candidates = [
        ("weights/best.pt", "model_weight", "best_model"),
        ("weights/last.pt", "model_weight", "last_model"),
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
    ]

    artifacts: List[Dict[str, Any]] = []
    for relative_path, artifact_type, role in candidates:
        entry = _artifact_entry(run_dir, relative_path, artifact_type, role)
        if entry:
            artifacts.append(entry)

    return {
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at": utc_now_iso(),
        "artifacts": artifacts,
    }


def write_artifact_manifest(run_dir: Path, run_id: str) -> Dict[str, Any]:
    import json

    manifest = build_artifact_manifest(run_dir, run_id)
    path = Path(run_dir) / "artifact_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
