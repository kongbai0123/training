from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


class RNNTrainingError(RuntimeError):
    pass


def train_rnn_from_dataset(
    dataset: Dict[str, Any],
    run_dir: Path,
    config: Dict[str, Any],
    stop_requested=None,
    progress_callback=None,
) -> Dict[str, Any]:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except Exception as exc:
        raise RNNTrainingError("PyTorch is required for RNNBackend MVP.") from exc

    run_dir.mkdir(parents=True, exist_ok=True)
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)

    task_head = dataset["task_head"]
    is_regression = task_head == "regression"
    device = _resolve_device(config.get("device"), torch)
    model_name = str(config.get("model") or "lstm").lower()
    hidden_size = max(1, int(config.get("hidden_size") or 128))
    num_layers = max(1, int(config.get("num_layers") or 2))
    dropout = float(config.get("dropout") or 0.0)
    bidirectional = bool(config.get("bidirectional")) or model_name == "bilstm"
    recurrent_type = "gru" if "gru" in model_name else "lstm"
    epochs = max(1, int(config.get("epochs") or 10))
    batch_size = max(1, int(config.get("batch_size") or 16))
    learning_rate = float(config.get("lr0") or 0.001)
    gradient_clip_norm = max(0.0, float(config.get("gradient_clip_norm") or 0.0))
    early_stopping_patience = max(0, int(config.get("early_stopping_patience") or 0))

    model = SequenceRNN(
        input_dim=dataset["input_dim"],
        hidden_size=hidden_size,
        num_layers=num_layers,
        num_outputs=dataset["num_outputs"],
        recurrent_type=recurrent_type,
        dropout=dropout,
        bidirectional=bidirectional,
        regression=is_regression,
    ).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.MSELoss() if is_regression else nn.CrossEntropyLoss()
    train_loader = _loader(dataset["tensors"]["train"], batch_size, torch, TensorDataset, DataLoader, shuffle=True)
    val_loader = _loader(dataset["tensors"]["val"], batch_size, torch, TensorDataset, DataLoader, shuffle=False)

    best_score: Optional[float] = None
    best_epoch = 0
    history: List[Dict[str, Any]] = []

    epochs_without_improvement = 0
    stopped_reason = ""

    for epoch in range(1, epochs + 1):
        if stop_requested and stop_requested():
            stopped_reason = "stop_requested"
            break

        train_loss = _run_epoch(model, train_loader, criterion, optimizer, device, is_regression, gradient_clip_norm)
        val_loss, predictions, targets = _evaluate(model, val_loader, criterion, device, is_regression)
        metric_row = _metrics(epoch, train_loss, val_loss, predictions, targets, is_regression)
        history.append(metric_row)

        score = metric_row["val/mae"] if is_regression else metric_row["val/macro_f1"]
        is_better = best_score is None or (score < best_score if is_regression else score > best_score)
        if is_better:
            best_score = score
            best_epoch = epoch
            epochs_without_improvement = 0
            _save_checkpoint(weights_dir / "best.pt", model, dataset, config, metric_row)
        else:
            epochs_without_improvement += 1

        _save_checkpoint(weights_dir / "last.pt", model, dataset, config, metric_row)
        if progress_callback:
            progress_callback(metric_row)
        if early_stopping_patience and epochs_without_improvement >= early_stopping_patience:
            stopped_reason = "early_stopping"
            break

    if not history:
        raise RNNTrainingError("RNN training stopped before the first epoch completed.")

    metrics_payload = {
        "backend": "pytorch_lstm",
        "architecture": "rnn",
        "task_type": "sequence_regression" if is_regression else "sequence_classification",
        "primary_metric": "val/mae" if is_regression else "val/macro_f1",
        "history": history,
        "best_epoch": best_epoch,
        "best_metrics": history[best_epoch - 1] if best_epoch else history[-1],
        "dataset_summary": dataset["summary"],
        "stopped_reason": stopped_reason,
        "early_stopping_patience": early_stopping_patience,
        "gradient_clip_norm": gradient_clip_norm,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_csv(run_dir / "results.csv", history)
    return metrics_payload


class SequenceRNN:
    def __new__(
        cls,
        input_dim: int,
        hidden_size: int,
        num_layers: int,
        num_outputs: int,
        recurrent_type: str,
        dropout: float,
        bidirectional: bool,
        regression: bool,
    ):
        import torch
        from torch import nn

        class _SequenceRNN(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                rnn_cls = nn.GRU if recurrent_type == "gru" else nn.LSTM
                self.rnn = rnn_cls(
                    input_size=input_dim,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=dropout if num_layers > 1 else 0.0,
                    bidirectional=bidirectional,
                )
                direction_factor = 2 if bidirectional else 1
                self.head = nn.Linear(hidden_size * direction_factor, 1 if regression else num_outputs)
                self.regression = regression

            def forward(self, x):
                output, _ = self.rnn(x)
                last = output[:, -1, :]
                y = self.head(last)
                return y.squeeze(-1) if self.regression else y

        return _SequenceRNN()


def _loader(split: Dict[str, Any], batch_size: int, torch, TensorDataset, DataLoader, shuffle: bool):
    x = torch.tensor(split["x"], dtype=torch.float32)
    y_dtype = torch.float32 if split["y"].dtype.kind == "f" else torch.long
    y = torch.tensor(split["y"], dtype=y_dtype)
    return DataLoader(TensorDataset(x, y), batch_size=batch_size, shuffle=shuffle)


def _run_epoch(model, loader, criterion, optimizer, device, is_regression: bool, gradient_clip_norm: float = 0.0) -> float:
    import torch

    model.train()
    losses = []
    for x, y in loader:
        x = x.to(device)
        y = y.to(device)
        optimizer.zero_grad()
        output = model(x)
        loss = criterion(output, y)
        loss.backward()
        if gradient_clip_norm > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), gradient_clip_norm)
        optimizer.step()
        losses.append(float(loss.detach().cpu().item()))
    return float(np.mean(losses)) if losses else 0.0


def _evaluate(model, loader, criterion, device, is_regression: bool):
    import torch

    model.eval()
    losses = []
    predictions = []
    targets = []
    with torch.no_grad():
        for x, y in loader:
            x = x.to(device)
            y = y.to(device)
            output = model(x)
            loss = criterion(output, y)
            losses.append(float(loss.detach().cpu().item()))
            if is_regression:
                predictions.extend(output.detach().cpu().numpy().reshape(-1).tolist())
                targets.extend(y.detach().cpu().numpy().reshape(-1).tolist())
            else:
                predictions.extend(output.argmax(dim=1).detach().cpu().numpy().reshape(-1).tolist())
                targets.extend(y.detach().cpu().numpy().reshape(-1).tolist())
    return float(np.mean(losses)) if losses else 0.0, predictions, targets


def _metrics(epoch: int, train_loss: float, val_loss: float, predictions: List[Any], targets: List[Any], is_regression: bool) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "epoch": epoch,
        "train/loss": round(train_loss, 6),
        "val/loss": round(val_loss, 6),
    }
    if is_regression:
        errors = np.asarray(predictions, dtype=float) - np.asarray(targets, dtype=float)
        row["val/mae"] = round(float(np.mean(np.abs(errors))), 6)
        row["val/rmse"] = round(float(math.sqrt(np.mean(errors ** 2))), 6)
        return row

    row.update(_classification_metrics(predictions, targets))
    return row


def _classification_metrics(predictions: List[Any], targets: List[Any]) -> Dict[str, float]:
    labels = sorted(set(predictions) | set(targets))
    total = len(targets) or 1
    accuracy = sum(1 for pred, target in zip(predictions, targets) if pred == target) / total
    precisions = []
    recalls = []
    f1s = []
    for label in labels:
        tp = sum(1 for pred, target in zip(predictions, targets) if pred == label and target == label)
        fp = sum(1 for pred, target in zip(predictions, targets) if pred == label and target != label)
        fn = sum(1 for pred, target in zip(predictions, targets) if pred != label and target == label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        precisions.append(precision)
        recalls.append(recall)
        f1s.append(f1)
    return {
        "val/accuracy": round(float(accuracy), 6),
        "val/precision": round(float(np.mean(precisions)) if precisions else 0.0, 6),
        "val/recall": round(float(np.mean(recalls)) if recalls else 0.0, 6),
        "val/macro_f1": round(float(np.mean(f1s)) if f1s else 0.0, 6),
    }


def _save_checkpoint(path: Path, model, dataset: Dict[str, Any], config: Dict[str, Any], metrics: Dict[str, Any]) -> None:
    import torch

    payload = {
        "model_state_dict": model.state_dict(),
        "config": {
            "model": config.get("model") or "lstm",
            "sequence_length": config.get("sequence_length"),
            "input_dim": dataset["input_dim"],
            "task_head": dataset["task_head"],
            "num_outputs": dataset["num_outputs"],
            "hidden_size": int(config.get("hidden_size") or 128),
            "num_layers": int(config.get("num_layers") or 2),
            "dropout": float(config.get("dropout") or 0.0),
            "bidirectional": bool(config.get("bidirectional")) or str(config.get("model") or "").lower() == "bilstm",
            "gradient_clip_norm": float(config.get("gradient_clip_norm") or 0.0),
            "early_stopping_patience": int(config.get("early_stopping_patience") or 0),
        },
        "feature_columns": dataset["feature_columns"],
        "target_column": dataset["target_column"],
        "label_encoder": dataset.get("label_encoder"),
        "normalization": dataset["normalization"],
        "metrics": metrics,
    }
    torch.save(payload, path)


def _write_results_csv(path: Path, history: List[Dict[str, Any]]) -> None:
    if not history:
        return
    import csv

    keys = list(history[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(history)


def _resolve_device(requested: Any, torch) -> str:
    requested_text = str(requested or "cpu").lower()
    if requested_text in {"gpu", "cuda", "0"} and torch.cuda.is_available():
        return "cuda"
    return "cpu"
