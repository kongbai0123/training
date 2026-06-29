from __future__ import annotations

import csv
import json
import shutil
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import numpy as np

from src.model_registry import ModelRegistry
from src.training.rnn.sequence_dataset import RNNSequenceDatasetError
from src.training.rnn.trainer import SequenceRNN


class RNNSequenceInferenceEngine:
    """CSV-only sequence inference for RNNBackend MVP."""

    @classmethod
    def run_csv_sequence_inference(
        cls,
        project: Dict[str, Any],
        model: Dict[str, Any],
        input_path: Path,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        cls._validate_rnn_model(model)
        cls._validate_input_csv(input_path)

        dirs = ModelRegistry.ensure_inference_dirs(project)
        project_id = project["project_id"]
        job_id = f"seq_job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"
        job_dir = dirs["jobs"] / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        input_copy = job_dir / f"input{input_path.suffix.lower()}"
        shutil.copy2(input_path, input_copy)

        started = time.perf_counter()
        checkpoint = cls._load_checkpoint(model["internal_weight_path"], settings.get("device", "cpu"))
        windows = cls._load_windows_from_csv(input_copy, checkpoint)
        predictions = cls._predict_windows(windows, checkpoint)
        inference_time_ms = round((time.perf_counter() - started) * 1000, 2)

        prediction_json = job_dir / "prediction.json"
        summary_json = job_dir / "summary.json"
        prediction_csv = job_dir / "predictions.csv"
        config_json = job_dir / "config.json"

        prediction_payload = {"predictions": predictions}
        summary = cls._build_summary(project_id, job_id, model, predictions, inference_time_ms, checkpoint)
        prediction_json.write_text(json.dumps(prediction_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        config_json.write_text(json.dumps({"model_id": model["model_id"], "settings": settings, "input": input_copy.name}, indent=2, ensure_ascii=False), encoding="utf-8")
        cls._write_prediction_csv(prediction_csv, predictions)

        return {
            "job_id": job_id,
            "model": model,
            "summary": summary,
            "predictions": predictions,
            "paths": {
                "job_dir": job_dir.resolve().as_posix(),
                "input_csv": input_copy.resolve().as_posix(),
                "prediction_json": prediction_json.resolve().as_posix(),
                "prediction_csv": prediction_csv.resolve().as_posix(),
                "summary_json": summary_json.resolve().as_posix(),
            },
            "urls": {
                "prediction_json": f"/api/projects/{project_id}/inference/jobs/{job_id}/files/{prediction_json.name}",
                "prediction_csv": f"/api/projects/{project_id}/inference/jobs/{job_id}/files/{prediction_csv.name}",
                "summary_json": f"/api/projects/{project_id}/inference/jobs/{job_id}/files/{summary_json.name}",
            },
        }

    @staticmethod
    def _validate_rnn_model(model: Dict[str, Any]) -> None:
        if model.get("architecture") != "rnn" and model.get("backend") != "pytorch_lstm":
            raise ValueError("Only RNN pytorch_lstm models are supported for sequence inference.")

    @staticmethod
    def _validate_input_csv(path: Path) -> None:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise ValueError("Input CSV does not exist.")
        if resolved.suffix.lower() != ".csv":
            raise ValueError("Only CSV feature sequence files are supported.")

    @staticmethod
    def _load_checkpoint(weight_path: str, requested_device: Any) -> Dict[str, Any]:
        try:
            import torch
        except Exception as exc:
            raise RuntimeError("PyTorch is required for RNN sequence inference.") from exc

        device = "cuda" if str(requested_device).lower() in {"gpu", "cuda", "0"} and torch.cuda.is_available() else "cpu"
        try:
            checkpoint = torch.load(weight_path, map_location=device, weights_only=True)
        except TypeError:
            checkpoint = torch.load(weight_path, map_location=device)
        config = checkpoint.get("config") or {}
        model_name = str(config.get("model") or "lstm").lower()
        model = SequenceRNN(
            input_dim=int(config.get("input_dim") or len(checkpoint.get("feature_columns") or [])),
            hidden_size=int(config.get("hidden_size") or 128),
            num_layers=int(config.get("num_layers") or 2),
            num_outputs=int(config.get("num_outputs") or 1),
            recurrent_type="gru" if "gru" in model_name else "lstm",
            dropout=float(config.get("dropout") or 0.0),
            bidirectional=bool(config.get("bidirectional")) or model_name == "bilstm",
            regression=str(config.get("task_head") or "").lower() == "regression",
        ).to(device)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
        checkpoint["runtime_model"] = model
        checkpoint["runtime_device"] = device
        return checkpoint

    @classmethod
    def _load_windows_from_csv(cls, path: Path, checkpoint: Dict[str, Any]) -> List[Dict[str, Any]]:
        feature_columns = checkpoint.get("feature_columns") or []
        target_column = checkpoint.get("target_column")
        config = checkpoint.get("config") or {}
        sequence_length = int(config.get("sequence_length") or 16)
        normalization = checkpoint.get("normalization") or {}
        mean = np.asarray(normalization.get("mean") or [0.0] * len(feature_columns), dtype=np.float32)
        std = np.asarray(normalization.get("std") or [1.0] * len(feature_columns), dtype=np.float32)
        std = np.where(std < 1e-8, 1.0, std)

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            missing = [column for column in ["sequence_id", *feature_columns] if column not in headers]
            if missing:
                raise RNNSequenceDatasetError(f"CSV missing required columns: {', '.join(missing)}")
            rows = [row for row in reader if str(row.get("sequence_id") or "").strip()]

        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["sequence_id"]).strip()].append(row)

        windows: List[Dict[str, Any]] = []
        for sequence_id, sequence_rows in grouped.items():
            ordered = sorted(sequence_rows, key=lambda row: _sort_value(row.get("timestep")))
            if len(ordered) < sequence_length:
                continue
            chunk = ordered[-sequence_length:]
            features = np.asarray([[float(row[col]) for col in feature_columns] for row in chunk], dtype=np.float32)
            features = (features - mean.reshape(1, -1)) / std.reshape(1, -1)
            windows.append(
                {
                    "sequence_id": sequence_id,
                    "features": features,
                    "target": chunk[-1].get(target_column) if target_column else None,
                }
            )

        if not windows:
            raise RNNSequenceDatasetError("No valid sequence windows could be built from CSV.")
        return windows

    @staticmethod
    def _predict_windows(windows: List[Dict[str, Any]], checkpoint: Dict[str, Any]) -> List[Dict[str, Any]]:
        import torch

        model = checkpoint["runtime_model"]
        device = checkpoint["runtime_device"]
        label_encoder = checkpoint.get("label_encoder") or {}
        inverse_labels = {int(value): key for key, value in label_encoder.items()}
        regression = str((checkpoint.get("config") or {}).get("task_head") or "").lower() == "regression"
        predictions: List[Dict[str, Any]] = []

        with torch.no_grad():
            for item in windows:
                x = torch.tensor(item["features"][None, :, :], dtype=torch.float32).to(device)
                output = model(x)
                if regression:
                    value = float(output.detach().cpu().numpy().reshape(-1)[0])
                    predictions.append({"sequence_id": item["sequence_id"], "prediction": value, "target": item.get("target")})
                else:
                    probs = torch.softmax(output, dim=1).detach().cpu().numpy().reshape(-1)
                    class_idx = int(np.argmax(probs))
                    predictions.append(
                        {
                            "sequence_id": item["sequence_id"],
                            "prediction": inverse_labels.get(class_idx, str(class_idx)),
                            "confidence": round(float(probs[class_idx]), 6),
                            "target": item.get("target"),
                        }
                    )
        return predictions

    @staticmethod
    def _build_summary(
        project_id: str,
        job_id: str,
        model: Dict[str, Any],
        predictions: List[Dict[str, Any]],
        inference_time_ms: float,
        checkpoint: Dict[str, Any],
    ) -> Dict[str, Any]:
        labels = sorted({str(item.get("prediction")) for item in predictions})
        return {
            "project_id": project_id,
            "job_id": job_id,
            "model_id": model["model_id"],
            "run_id": model.get("run_id"),
            "architecture": "rnn",
            "backend": "pytorch_lstm",
            "task_type": model.get("task_type"),
            "sequence_count": len(predictions),
            "predicted_labels": labels,
            "inference_time_ms": inference_time_ms,
            "created_at": datetime.now().isoformat(),
            "device": checkpoint.get("runtime_device", "cpu"),
        }

    @staticmethod
    def _write_prediction_csv(path: Path, predictions: List[Dict[str, Any]]) -> None:
        keys = ["sequence_id", "prediction", "confidence", "target"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            for item in predictions:
                writer.writerow({key: item.get(key, "") for key in keys})


def _sort_value(value: Any) -> tuple[int, float | str]:
    try:
        return (0, float(value))
    except (TypeError, ValueError):
        return (1, str(value or ""))
