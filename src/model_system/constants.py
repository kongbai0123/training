from __future__ import annotations

from pathlib import Path

from src.config import BASE_DIR


BUILTIN_MODEL_CATALOG_PATH = BASE_DIR / "data" / "builtin_model_catalog.json"
MODEL_DECISION_METADATA_PATH = BASE_DIR / "data" / "model_decision_metadata.json"
MODEL_MANIFEST_NAME = "model_manifest.json"
SOURCE_MODEL_MANIFEST_NAME = "source_model_manifest.json"
CUSTOM_PACKAGE_SOURCE_MANIFEST_NAMES = (
    "manifest.yaml",
    "manifest.yml",
    "model_manifest.yaml",
    "model_manifest.yml",
    "model_manifest.json",
)
VALIDATION_REPORT_NAME = "validation_report.json"
IMPORTED_MODELS_RELATIVE_DIR = Path("models") / "imports"

MODEL_STATUS_AVAILABLE = "available"
MODEL_STATUS_NOT_INSTALLED = "not_installed"
MODEL_STATUS_INSTALLING = "installing"
MODEL_STATUS_CORRUPT = "corrupt"
MODEL_STATUS_INCOMPATIBLE = "incompatible"
MODEL_STATUS_VALIDATED = "validated"
MODEL_STATUS_VALIDATED_BASIC = "validated_basic"
MODEL_STATUS_FAILED = "failed"
MODEL_STATUS_MISSING_FILE = "missing_file"
MODEL_STATUS_REGISTERED_DISABLED = "REGISTERED_DISABLED"
MODEL_STATUS_READY_FOR_REVIEW = "READY_FOR_REVIEW"
MODEL_STATUS_REJECTED = "REJECTED"
