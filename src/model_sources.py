from __future__ import annotations

from typing import Any, Dict, List


def list_model_sources() -> List[Dict[str, Any]]:
    return [
        {
            "source_id": "official_ultralytics",
            "architecture": "cnn",
            "label": "Official Ultralytics models",
            "formats": ["pt"],
            "availability": "installable",
            "network_required": True,
            "confirmation_required": True,
            "security_policy": "allowlisted_https_sha256",
        },
        {
            "source_id": "custom_yolo",
            "architecture": "cnn",
            "label": "Custom YOLO model",
            "formats": ["pt", "yaml", "yml"],
            "availability": "project_import",
            "network_required": False,
            "confirmation_required": False,
            "security_policy": "project_scoped_validation",
        },
        {
            "source_id": "project_checkpoints",
            "architecture": "cnn_rnn",
            "label": "Project best / last checkpoints",
            "formats": ["pt"],
            "availability": "auto_discovered",
            "network_required": False,
            "confirmation_required": False,
            "security_policy": "managed_project_paths",
        },
        {
            "source_id": "rnn_templates",
            "architecture": "rnn",
            "label": "Built-in RNN / XGBoost templates",
            "formats": ["template"],
            "availability": "built_in",
            "network_required": False,
            "confirmation_required": False,
            "security_policy": "application_code_only",
        },
        {
            "source_id": "external_pytorch_package",
            "architecture": "cnn_rnn",
            "label": "External PyTorch package",
            "formats": ["zip"],
            "availability": "validation_only",
            "network_required": False,
            "confirmation_required": True,
            "security_policy": "manifest_validation_manual_approval_no_code_execution",
        },
    ]
