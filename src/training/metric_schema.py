from __future__ import annotations

from typing import Any, Dict

from src.training.contracts import CONTRACT_VERSION


def _is_segmentation(task_type: str) -> bool:
    normalized = str(task_type or "").lower()
    return "segmentation" in normalized or "seg" in normalized


def build_yolo_metric_schema(task_type: str) -> Dict[str, Any]:
    is_seg = _is_segmentation(task_type)
    suffix = "(M)" if is_seg else "(B)"

    loss_group = ["train/box_loss", "val/box_loss"]
    if is_seg:
        loss_group.extend(["train/seg_loss", "val/seg_loss"])

    return {
        "contract_version": CONTRACT_VERSION,
        "primary_metric": {
            "key": f"metrics/mAP50-95{suffix}",
            "display_name": "mAP50-95",
            "goal": "maximize",
        },
        "groups": {
            "loss": loss_group,
            "quality": [
                f"metrics/mAP50{suffix}",
                f"metrics/mAP50-95{suffix}",
                f"metrics/precision{suffix}",
                f"metrics/recall{suffix}",
            ],
        },
    }


def build_rnn_metric_schema(task_type: str = "sequence_classification") -> Dict[str, Any]:
    normalized = str(task_type or "sequence_classification").lower()
    is_regression = "regression" in normalized

    if is_regression:
        primary_metric = {
            "key": "val/mae",
            "display_name": "MAE",
            "goal": "minimize",
        }
        quality = ["val/mae", "val/rmse"]
    else:
        primary_metric = {
            "key": "val/macro_f1",
            "display_name": "Macro-F1",
            "goal": "maximize",
        }
        quality = ["val/accuracy", "val/macro_f1", "val/precision", "val/recall"]

    return {
        "contract_version": CONTRACT_VERSION,
        "primary_metric": primary_metric,
        "groups": {
            "loss": ["train/loss", "val/loss"],
            "quality": quality,
        },
    }
