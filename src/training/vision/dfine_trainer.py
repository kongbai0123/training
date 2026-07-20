from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from src.project_layout import ProjectLayout


class DFineTrainingError(RuntimeError):
    pass


def train_dfine_model(project: Dict[str, Any], run_dir: Path, config: Dict[str, Any], *, stop_requested=None, progress_callback=None) -> Dict[str, Any]:
    os.environ.setdefault("USE_TF", "0")
    os.environ.setdefault("USE_FLAX", "0")
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
        from transformers import AutoImageProcessor, DFineForObjectDetection
    except Exception as exc:
        raise DFineTrainingError("D-FINE requires the bundled Transformers component.") from exc

    model_path = Path(str(config.get("model") or ""))
    if not model_path.is_absolute():
        from src.app_paths import MODELS_DIR

        model_path = Path(MODELS_DIR) / model_path.name
    if not (model_path / "config.json").exists():
        raise DFineTrainingError("Install D-FINE Small before training.")

    classes = list(project.get("class_names") or [])
    if not classes:
        raise DFineTrainingError("At least one class is required.")
    id2label = {index: label for index, label in enumerate(classes)}
    label2id = {label: index for index, label in id2label.items()}
    processor = AutoImageProcessor.from_pretrained(model_path, local_files_only=True)
    model = DFineForObjectDetection.from_pretrained(
        model_path,
        local_files_only=True,
        num_labels=len(classes),
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )
    device = torch.device("cuda:0" if str(config.get("device") or "").lower() in {"gpu", "cuda", "0"} and torch.cuda.is_available() else "cpu")
    model.to(device)

    train_dataset = _DFineDataset(project, "train")
    val_dataset = _DFineDataset(project, "val")
    if not train_dataset.items or not val_dataset.items:
        raise DFineTrainingError("D-FINE requires non-empty train and validation splits.")

    def collate(batch):
        images = [item[0] for item in batch]
        annotations = [item[1] for item in batch]
        return processor(images=images, annotations=annotations, return_tensors="pt")

    batch_size = max(1, int(config.get("batch_size") or 2))
    workers = max(0, int(config.get("workers") or 0))
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=workers, collate_fn=collate)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=workers, collate_fn=collate)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(config.get("lr0") or 1e-4), weight_decay=1e-4)
    epochs = max(1, int(config.get("epochs") or 10))
    patience = max(0, int(config.get("patience") or 0))
    history: List[Dict[str, Any]] = []
    best_loss = None
    best_epoch = 0
    stale = 0
    stopped_reason = ""
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, epochs + 1):
        if stop_requested and stop_requested():
            stopped_reason = "stop_requested"
            break
        train_loss = _run_epoch(model, train_loader, device, torch, optimizer)
        val_loss = _run_epoch(model, val_loader, device, torch, None)
        row = {"epoch": epoch, "loss": round(train_loss, 6), "train/loss": round(train_loss, 6), "val/loss": round(val_loss, 6)}
        history.append(row)
        improved = best_loss is None or val_loss < best_loss
        if improved:
            best_loss = val_loss
            best_epoch = epoch
            stale = 0
            _save_checkpoint(weights_dir / "best.pt", model, classes, config, row, torch)
        else:
            stale += 1
        _save_checkpoint(weights_dir / "last.pt", model, classes, config, row, torch)
        if progress_callback:
            progress_callback(row)
        if patience and stale >= patience:
            stopped_reason = "early_stopping"
            break

    if not history:
        raise DFineTrainingError("D-FINE training stopped before the first epoch completed.")
    payload = {
        "backend": "transformers_dfine",
        "architecture": "cnn",
        "task_type": "object_detection",
        "model": "dfine-small-coco",
        "primary_metric": "val/loss",
        "history": history,
        "best_epoch": best_epoch,
        "best_metrics": history[best_epoch - 1],
        "stopped_reason": stopped_reason,
        "dataset_summary": {"train": len(train_dataset), "val": len(val_dataset), "classes": classes},
    }
    (run_dir / "metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_csv(run_dir / "results.csv", history)
    return payload


class _DFineDataset:
    def __init__(self, project: Dict[str, Any], split: str) -> None:
        self.project = project
        self.layout = ProjectLayout.from_project(project)
        self.classes = list(project.get("class_names") or [])
        self.class_to_index = {name: index for index, name in enumerate(self.classes)}
        self.items = [item for item in project.get("images") or [] if item.get("split") == split and self._path(item).exists()]

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        item = self.items[index]
        with Image.open(self._path(item)) as source:
            image = source.convert("RGB")
            width, height = image.size
        annotations = []
        for annotation in item.get("annotations") or []:
            category = annotation.get("category")
            bbox = annotation.get("bbox") or []
            if category not in self.class_to_index or len(bbox) != 4:
                continue
            center_x, center_y, box_width, box_height = [float(value) for value in bbox]
            x = (center_x - box_width / 2) * width
            y = (center_y - box_height / 2) * height
            w, h = box_width * width, box_height * height
            annotations.append({"id": len(annotations), "image_id": index, "category_id": self.class_to_index[category], "bbox": [x, y, w, h], "area": w * h, "iscrowd": 0})
        return image, {"image_id": index, "annotations": annotations}

    def _path(self, item):
        return self.layout.resolve_raw_images_dir().path / str(item.get("filename") or "")


def _run_epoch(model, loader, device, torch, optimizer):
    model.train(mode=optimizer is not None)
    losses = []
    context = torch.enable_grad() if optimizer is not None else torch.no_grad()
    with context:
        for batch in loader:
            values = {key: value.to(device) if hasattr(value, "to") else value for key, value in batch.items()}
            if "labels" in values:
                values["labels"] = [{key: value.to(device) for key, value in label.items()} for label in values["labels"]]
            if optimizer is not None:
                optimizer.zero_grad(set_to_none=True)
            output = model(**values)
            loss = output.loss
            if optimizer is not None:
                loss.backward()
                optimizer.step()
            losses.append(float(loss.detach().cpu().item()))
    return sum(losses) / max(1, len(losses))


def _save_checkpoint(path, model, classes, config, metrics, torch):
    torch.save({"format": "vision_training_studio.dfine.v1", "model_key": "dfine-small", "task_type": "object_detection", "class_names": classes, "state_dict": model.state_dict(), "config": dict(config), "metrics": dict(metrics)}, path)


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
