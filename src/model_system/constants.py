from __future__ import annotations

from pathlib import Path

from src.config import BASE_DIR


BUILTIN_MODEL_CATALOG_PATH = BASE_DIR / "data" / "builtin_model_catalog.json"
MODEL_MANIFEST_NAME = "model_manifest.json"
VALIDATION_REPORT_NAME = "validation_report.json"
IMPORTED_MODELS_RELATIVE_DIR = Path("models") / "imports"

MODEL_STATUS_AVAILABLE = "available"
MODEL_STATUS_VALIDATED = "validated"
MODEL_STATUS_VALIDATED_BASIC = "validated_basic"
MODEL_STATUS_FAILED = "failed"
MODEL_STATUS_MISSING_FILE = "missing_file"
MODEL_STATUS_REGISTERED_DISABLED = "REGISTERED_DISABLED"
MODEL_STATUS_READY_FOR_REVIEW = "READY_FOR_REVIEW"
MODEL_STATUS_REJECTED = "REJECTED"
