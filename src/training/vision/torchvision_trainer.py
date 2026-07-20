from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from PIL import Image, ImageDraw

from src.app_paths import MODELS_DIR
from src.project_layout import ProjectLayout


class TorchVisionTrainingError(RuntimeError):
    pass


def validate_torchvision_model_install(model_value: Any) -> str | None:
    model_key = _model_key(model_value)
    if model_key == "unet":
        return None
    try:
        _installed_weight_path(model_key)
        return None
    except TorchVisionTrainingError as exc:
        return str(exc)


CLASSIFICATION_MODELS = {
    "resnet18": "resnet18",
    "mobilenet_v3_large": "mobilenet_v3_large",
    "efficientnet_b0": "efficientnet_b0",
}
DETECTION_MODELS = {
    "fasterrcnn_mobilenet_v3_large_fpn": "fasterrcnn_mobilenet_v3_large_fpn",
    "fasterrcnn_resnet50_fpn": "fasterrcnn_resnet50_fpn_v2",
    "fcos_resnet50_fpn": "fcos_resnet50_fpn",
}
INSTANCE_MODELS = {"maskrcnn_resnet50_fpn": "maskrcnn_resnet50_fpn_v2"}
SEMANTIC_MODELS = {
    "deeplabv3_mobilenet_v3_large": "deeplabv3_mobilenet_v3_large",
    "deeplabv3_resnet50": "deeplabv3_resnet50",
    "unet": "unet",
}


def train_torchvision_model(
    project: Dict[str, Any],
    run_dir: Path,
    config: Dict[str, Any],
    *,
    stop_requested=None,
    progress_callback=None,
) -> Dict[str, Any]:
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader
    except Exception as exc:
        raise TorchVisionTrainingError("PyTorch and TorchVision are required for this visual model.") from exc

    task = _task_category(project.get("task_type"))
    model_key = _model_key(config.get("model"))
    classes = list(project.get("class_names") or [])
    if not classes:
        raise TorchVisionTrainingError("At least one class is required.")

    image_size = max(64, int(config.get("imgsz") or 640))
    batch_size = max(1, int(config.get("batch_size") or 4))
    workers = max(0, int(config.get("workers") or 0))
    epochs = max(1, int(config.get("epochs") or 10))
    patience = max(0, int(config.get("patience") or 0))
    device = _resolve_device(config.get("device"), torch)

    train_dataset = ProjectVisionDataset(project, "train", task, image_size, torch)
    val_dataset = ProjectVisionDataset(project, "val", task, image_size, torch)
    if not train_dataset.items:
        raise TorchVisionTrainingError("The training split has no usable images.")
    if not val_dataset.items:
        raise TorchVisionTrainingError("The validation split has no usable images.")

    collate = _detection_collate if task in {"object_detection", "instance_segmentation"} else None
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=workers, collate_fn=collate)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=workers, collate_fn=collate)

    model = _build_model(model_key, task, len(classes), torch, nn).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=float(config.get("lr0") or 0.001), weight_decay=1e-4)
    scaler = torch.amp.GradScaler("cuda", enabled=bool(config.get("amp")) and device.type == "cuda")
    criterion = nn.CrossEntropyLoss()

    run_dir.mkdir(parents=True, exist_ok=True)
    weights_dir = run_dir / "weights"
    weights_dir.mkdir(parents=True, exist_ok=True)
    history: List[Dict[str, Any]] = []
    best_score = None
    best_epoch = 0
    stale_epochs = 0
    stopped_reason = ""

    for epoch in range(1, epochs + 1):
        if stop_requested and stop_requested():
            stopped_reason = "stop_requested"
            break
        train_loss = _train_epoch(model, train_loader, optimizer, scaler, criterion, task, device, torch)
        val_loss, quality = _validate_epoch(model, val_loader, criterion, task, device, torch, len(classes))
        row = _metric_row(epoch, train_loss, val_loss, quality, task)
        history.append(row)

        score, maximize = _score(row, task)
        improved = best_score is None or (score > best_score if maximize else score < best_score)
        if improved:
            best_score = score
            best_epoch = epoch
            stale_epochs = 0
            _save_checkpoint(weights_dir / "best.pt", model, model_key, task, classes, config, row, torch)
        else:
            stale_epochs += 1
        _save_checkpoint(weights_dir / "last.pt", model, model_key, task, classes, config, row, torch)
        if progress_callback:
            progress_callback(row)
        if patience and stale_epochs >= patience:
            stopped_reason = "early_stopping"
            break

    if not history:
        raise TorchVisionTrainingError("Training stopped before the first epoch completed.")

    best_metrics = history[best_epoch - 1] if best_epoch else history[-1]
    payload = {
        "backend": "pytorch_torchvision",
        "architecture": "cnn",
        "task_type": task,
        "model": model_key,
        "primary_metric": _primary_metric(task),
        "history": history,
        "best_epoch": best_epoch,
        "best_metrics": best_metrics,
        "stopped_reason": stopped_reason,
        "dataset_summary": {"train": len(train_dataset), "val": len(val_dataset), "classes": classes},
    }
    (run_dir / "metrics.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_results_csv(run_dir / "results.csv", history)
    return payload


class ProjectVisionDataset:
    def __init__(self, project: Dict[str, Any], split: str, task: str, image_size: int, torch_module) -> None:
        self.project = project
        self.split = split
        self.task = task
        self.image_size = image_size
        self.torch = torch_module
        self.class_names = list(project.get("class_names") or [])
        self.class_to_index = {name: index for index, name in enumerate(self.class_names)}
        self.layout = ProjectLayout.from_project(project)
        self.items = [item for item in project.get("images") or [] if item.get("split") == split and self._image_path(item).exists()]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int):
        item = self.items[index]
        path = self._image_path(item)
        with Image.open(path) as source:
            image = source.convert("RGB")
            original_size = image.size
            image = image.resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
        if self.task == "image_classification":
            return self._normalized_tensor(image), self._classification_label(item)
        if self.task == "semantic_segmentation":
            return self._normalized_tensor(image), self._semantic_mask(item, original_size)
        tensor = self._plain_tensor(image)
        return tensor, self._detection_target(item, original_size, include_masks=self.task == "instance_segmentation")

    def _image_path(self, item: Dict[str, Any]) -> Path:
        if item.get("is_augmented"):
            job_id = item.get("augmentation_job_id") or item.get("aug_job_id")
            if job_id:
                return self.layout.augmentation_outputs_dir(str(job_id)) / "images" / str(item.get("filename") or "")
        return self.layout.resolve_raw_images_dir().path / str(item.get("filename") or "")

    def _plain_tensor(self, image: Image.Image):
        import numpy as np

        array = np.asarray(image, dtype="float32").transpose(2, 0, 1) / 255.0
        return self.torch.from_numpy(array)

    def _normalized_tensor(self, image: Image.Image):
        tensor = self._plain_tensor(image)
        mean = self.torch.tensor([0.485, 0.456, 0.406], dtype=tensor.dtype)[:, None, None]
        std = self.torch.tensor([0.229, 0.224, 0.225], dtype=tensor.dtype)[:, None, None]
        return (tensor - mean) / std

    def _classification_label(self, item: Dict[str, Any]):
        explicit = item.get("class_name") or item.get("category") or item.get("label")
        annotations = item.get("annotations") or []
        label = explicit or (annotations[0].get("category") if annotations else None)
        if label not in self.class_to_index:
            raise TorchVisionTrainingError(
                f"Image '{item.get('filename')}' needs one image-level class. Set class_name or add one class annotation."
            )
        return self.torch.tensor(self.class_to_index[label], dtype=self.torch.long)

    def _detection_target(self, item: Dict[str, Any], original_size: Tuple[int, int], include_masks: bool):
        boxes: List[List[float]] = []
        labels: List[int] = []
        masks: List[Any] = []
        width, height = original_size
        for annotation in item.get("annotations") or []:
            category = annotation.get("category")
            if category not in self.class_to_index:
                continue
            box = _normalized_xyxy(annotation, width, height)
            if box is None:
                continue
            boxes.append([value * self.image_size for value in box])
            labels.append(self.class_to_index[category] + 1)
            if include_masks:
                masks.append(_annotation_mask(annotation, width, height, self.image_size, self.torch))
        target = {
            "boxes": self.torch.tensor(boxes, dtype=self.torch.float32).reshape(-1, 4),
            "labels": self.torch.tensor(labels, dtype=self.torch.int64),
            "image_id": self.torch.tensor([abs(hash(str(item.get("filename")))) % (2**31)], dtype=self.torch.int64),
        }
        if include_masks:
            target["masks"] = self.torch.stack(masks) if masks else self.torch.zeros((0, self.image_size, self.image_size), dtype=self.torch.uint8)
        return target

    def _semantic_mask(self, item: Dict[str, Any], original_size: Tuple[int, int]):
        width, height = original_size
        canvas = Image.new("L", (self.image_size, self.image_size), 0)
        draw = ImageDraw.Draw(canvas)
        for annotation in item.get("annotations") or []:
            category = annotation.get("category")
            if category not in self.class_to_index:
                continue
            points = annotation.get("points") or []
            if len(points) >= 3:
                scaled = [(float(x) / width * self.image_size, float(y) / height * self.image_size) for x, y in points]
                draw.polygon(scaled, fill=self.class_to_index[category] + 1)
            else:
                box = _normalized_xyxy(annotation, width, height)
                if box:
                    draw.rectangle(tuple(value * self.image_size for value in box), fill=self.class_to_index[category] + 1)
        import numpy as np

        return self.torch.from_numpy(np.asarray(canvas, dtype="int64").copy())


def _build_model(model_key: str, task: str, class_count: int, torch, nn):
    try:
        import torchvision.models as models
        import torchvision.models.detection as detection
        import torchvision.models.segmentation as segmentation
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
        from torchvision.models.detection.fcos import FCOSClassificationHead
        from torchvision.models.detection.mask_rcnn import MaskRCNNPredictor
    except Exception as exc:
        raise TorchVisionTrainingError("TorchVision could not be loaded.") from exc

    weights_path = _installed_weight_path(model_key)
    if model_key in CLASSIFICATION_MODELS:
        model = getattr(models, CLASSIFICATION_MODELS[model_key])(weights=None)
        _load_state_dict(model, weights_path, torch)
        if model_key == "resnet18":
            model.fc = nn.Linear(model.fc.in_features, class_count)
        else:
            last = model.classifier[-1]
            model.classifier[-1] = nn.Linear(last.in_features, class_count)
        return model
    if model_key in DETECTION_MODELS:
        model = getattr(detection, DETECTION_MODELS[model_key])(weights=None, weights_backbone=None)
        _load_state_dict(model, weights_path, torch)
        if model_key.startswith("fasterrcnn"):
            model.roi_heads.box_predictor = FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features, class_count + 1)
        else:
            anchors = model.anchor_generator.num_anchors_per_location()[0]
            model.head.classification_head = FCOSClassificationHead(model.backbone.out_channels, anchors, class_count + 1)
        return model
    if model_key in INSTANCE_MODELS:
        model = getattr(detection, INSTANCE_MODELS[model_key])(weights=None, weights_backbone=None)
        _load_state_dict(model, weights_path, torch)
        box_features = model.roi_heads.box_predictor.cls_score.in_features
        mask_features = model.roi_heads.mask_predictor.conv5_mask.in_channels
        model.roi_heads.box_predictor = FastRCNNPredictor(box_features, class_count + 1)
        model.roi_heads.mask_predictor = MaskRCNNPredictor(mask_features, 256, class_count + 1)
        return model
    if model_key in SEMANTIC_MODELS:
        if model_key == "unet":
            return _SmallUNet(class_count + 1, nn)
        model = getattr(segmentation, SEMANTIC_MODELS[model_key])(weights=None, weights_backbone=None, aux_loss=True)
        _load_state_dict(model, weights_path, torch)
        model.classifier[-1] = nn.Conv2d(model.classifier[-1].in_channels, class_count + 1, kernel_size=1)
        if getattr(model, "aux_classifier", None) is not None:
            model.aux_classifier[-1] = nn.Conv2d(model.aux_classifier[-1].in_channels, class_count + 1, kernel_size=1)
        return model
    raise TorchVisionTrainingError(f"Unsupported TorchVision model: {model_key}")


def _SmallUNet(num_classes: int, nn):
    class Block(nn.Module):
        def __init__(self, input_channels: int, output_channels: int) -> None:
            super().__init__()
            self.layers = nn.Sequential(
                nn.Conv2d(input_channels, output_channels, 3, padding=1), nn.BatchNorm2d(output_channels), nn.ReLU(inplace=True),
                nn.Conv2d(output_channels, output_channels, 3, padding=1), nn.BatchNorm2d(output_channels), nn.ReLU(inplace=True),
            )

        def forward(self, value):
            return self.layers(value)

    class UNet(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.enc1, self.enc2, self.enc3 = Block(3, 32), Block(32, 64), Block(64, 128)
            self.pool = nn.MaxPool2d(2)
            self.up2, self.up1 = nn.ConvTranspose2d(128, 64, 2, 2), nn.ConvTranspose2d(64, 32, 2, 2)
            self.dec2, self.dec1 = Block(128, 64), Block(64, 32)
            self.head = nn.Conv2d(32, num_classes, 1)

        def forward(self, value):
            e1 = self.enc1(value)
            e2 = self.enc2(self.pool(e1))
            center = self.enc3(self.pool(e2))
            d2 = self.dec2(__import__("torch").cat([self.up2(center), e2], dim=1))
            d1 = self.dec1(__import__("torch").cat([self.up1(d2), e1], dim=1))
            return {"out": self.head(d1)}

    return UNet()


def _train_epoch(model, loader, optimizer, scaler, criterion, task, device, torch) -> float:
    model.train()
    losses = []
    for batch in loader:
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device_type=device.type, enabled=scaler.is_enabled()):
            if task in {"object_detection", "instance_segmentation"}:
                images, targets = batch
                images = [image.to(device) for image in images]
                targets = [{key: value.to(device) for key, value in target.items()} for target in targets]
                output = model(images, targets)
                loss = sum(output.values())
            else:
                images, targets = batch[0].to(device), batch[1].to(device)
                output = model(images)
                logits = output["out"] if isinstance(output, dict) else output
                loss = criterion(logits, targets)
                if isinstance(output, dict) and output.get("aux") is not None:
                    loss = loss + 0.4 * criterion(output["aux"], targets)
        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()
        losses.append(float(loss.detach().cpu().item()))
    return sum(losses) / max(1, len(losses))


def _validate_epoch(model, loader, criterion, task, device, torch, class_count):
    losses = []
    correct = total = 0
    intersection = torch.zeros(class_count + 1, dtype=torch.float64)
    union = torch.zeros(class_count + 1, dtype=torch.float64)
    if task in {"object_detection", "instance_segmentation"}:
        model.train()
    else:
        model.eval()
    with torch.no_grad():
        for batch in loader:
            if task in {"object_detection", "instance_segmentation"}:
                images, targets = batch
                images = [image.to(device) for image in images]
                targets = [{key: value.to(device) for key, value in target.items()} for target in targets]
                output = model(images, targets)
                losses.append(float(sum(output.values()).detach().cpu().item()))
            else:
                images, targets = batch[0].to(device), batch[1].to(device)
                output = model(images)
                logits = output["out"] if isinstance(output, dict) else output
                losses.append(float(criterion(logits, targets).detach().cpu().item()))
                predictions = logits.argmax(dim=1)
                if task == "image_classification":
                    correct += int((predictions == targets).sum().item())
                    total += int(targets.numel())
                else:
                    for label in range(1, class_count + 1):
                        pred_mask = predictions == label
                        target_mask = targets == label
                        intersection[label] += (pred_mask & target_mask).sum().cpu()
                        union[label] += (pred_mask | target_mask).sum().cpu()
    quality: Dict[str, float] = {}
    if task == "image_classification":
        quality["accuracy"] = correct / max(1, total)
    elif task == "semantic_segmentation":
        valid = union[1:] > 0
        quality["mean_iou"] = float((intersection[1:][valid] / union[1:][valid]).mean().item()) if valid.any() else 0.0
    return sum(losses) / max(1, len(losses)), quality


def _metric_row(epoch, train_loss, val_loss, quality, task):
    row = {"epoch": epoch, "loss": round(train_loss, 6), "train/loss": round(train_loss, 6), "val/loss": round(val_loss, 6)}
    if task == "image_classification":
        row["val/accuracy"] = round(float(quality.get("accuracy", 0.0)), 6)
    elif task == "semantic_segmentation":
        row["val/mean_iou"] = round(float(quality.get("mean_iou", 0.0)), 6)
    return row


def _score(row, task):
    if task == "image_classification":
        return float(row.get("val/accuracy", 0.0)), True
    if task == "semantic_segmentation":
        return float(row.get("val/mean_iou", 0.0)), True
    return float(row.get("val/loss", math.inf)), False


def _primary_metric(task):
    if task == "image_classification":
        return "val/accuracy"
    if task == "semantic_segmentation":
        return "val/mean_iou"
    return "val/loss"


def _save_checkpoint(path, model, model_key, task, classes, config, metrics, torch):
    torch.save({
        "format": "vision_training_studio.torchvision.v1",
        "model_key": model_key,
        "task_type": task,
        "class_names": classes,
        "state_dict": model.state_dict(),
        "config": dict(config),
        "metrics": dict(metrics),
    }, path)


def _load_state_dict(model, path: Path | None, torch):
    if path is None:
        return
    payload = torch.load(path, map_location="cpu", weights_only=True)
    state_dict = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
    model.load_state_dict(state_dict, strict=True)


def _installed_weight_path(model_key: str) -> Path | None:
    candidates = list(Path(MODELS_DIR).glob(f"{model_key}*.pt")) + list(Path(MODELS_DIR).glob(f"{model_key}*.pth"))
    if candidates:
        return candidates[0]
    if model_key == "unet":
        return None
    raise TorchVisionTrainingError(f"Install the pretrained weights for '{model_key}' before training.")


def _model_key(value: Any) -> str:
    stem = Path(str(value or "")).stem.lower().replace("-", "_")
    aliases = {
        "resnet18_imagenet1k_v1": "resnet18",
        "mobilenet_v3_large_imagenet1k_v2": "mobilenet_v3_large",
        "efficientnet_b0_imagenet1k_v1": "efficientnet_b0",
        "fasterrcnn_mobilenet_v3_large_fpn_coco": "fasterrcnn_mobilenet_v3_large_fpn",
        "fasterrcnn_resnet50_fpn_v2_coco": "fasterrcnn_resnet50_fpn",
        "fcos_resnet50_fpn_coco": "fcos_resnet50_fpn",
        "maskrcnn_resnet50_fpn_v2_coco": "maskrcnn_resnet50_fpn",
        "deeplabv3_mobilenet_v3_large_coco": "deeplabv3_mobilenet_v3_large",
        "deeplabv3_resnet50_coco": "deeplabv3_resnet50",
    }
    return aliases.get(stem, stem)


def _task_category(value: Any) -> str:
    task = str(value or "").lower()
    if "classif" in task and "sequence" not in task:
        return "image_classification"
    if "semantic" in task:
        return "semantic_segmentation"
    if "instance" in task or task == "segmentation":
        return "instance_segmentation"
    if "detect" in task:
        return "object_detection"
    return task


def _normalized_xyxy(annotation, width, height):
    bbox = annotation.get("bbox") or []
    if len(bbox) == 4:
        cx, cy, box_width, box_height = [float(value) for value in bbox]
        return [max(0.0, cx - box_width / 2), max(0.0, cy - box_height / 2), min(1.0, cx + box_width / 2), min(1.0, cy + box_height / 2)]
    points = annotation.get("points") or []
    if points:
        xs, ys = [float(point[0]) for point in points], [float(point[1]) for point in points]
        return [max(0.0, min(xs) / width), max(0.0, min(ys) / height), min(1.0, max(xs) / width), min(1.0, max(ys) / height)]
    return None


def _annotation_mask(annotation, width, height, image_size, torch):
    canvas = Image.new("L", (image_size, image_size), 0)
    draw = ImageDraw.Draw(canvas)
    points = annotation.get("points") or []
    if len(points) >= 3:
        draw.polygon([(float(x) / width * image_size, float(y) / height * image_size) for x, y in points], fill=1)
    else:
        box = _normalized_xyxy(annotation, width, height)
        if box:
            draw.rectangle(tuple(value * image_size for value in box), fill=1)
    import numpy as np

    return torch.from_numpy(np.asarray(canvas, dtype="uint8").copy())


def _detection_collate(batch: Sequence[Tuple[Any, Any]]):
    return tuple(zip(*batch))


def _resolve_device(value, torch):
    requested = str(value or "cpu").lower()
    if requested in {"gpu", "cuda", "0"} and torch.cuda.is_available():
        return torch.device("cuda:0")
    return torch.device("cpu")


def _write_results_csv(path: Path, history: Iterable[Dict[str, Any]]) -> None:
    rows = list(history)
    keys: List[str] = []
    for row in rows:
        for key in row:
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)
