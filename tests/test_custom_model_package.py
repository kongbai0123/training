import tempfile
import unittest
import zipfile
from pathlib import Path

from src.custom_model_package import CustomModelPackageValidator


VALID_MANIFEST = """
model:
  name: Custom Road Model
  architecture: cnn
  task_type: segmentation
  framework: pytorch

entrypoints:
  trainer: train.train
  predictor: predict.predict

input:
  type: image
  shape: [3, 640, 640]

output:
  type: segmentation_mask
  classes: [asphalt, cement, gravel]

metrics:
  required: [train/loss, val/loss]
  optional: [precision, recall, f1, miou]

security:
  allow_network: false
  allow_shell: false
  allow_write: project_only
"""


class CustomModelPackageValidatorTests(unittest.TestCase):
    def test_valid_manifest_yaml_is_understood_but_not_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "custom_model_package.zip"
            with zipfile.ZipFile(package_path, "w") as zf:
                zf.writestr("manifest.yaml", VALID_MANIFEST)
                zf.writestr("train.py", "def train():\n    return {}\n")
                zf.writestr("predict.py", "def predict():\n    return {}\n")

            result = CustomModelPackageValidator.validate_zip(package_path)

        self.assertEqual("valid_manifest_execution_disabled", result["status"])
        self.assertTrue(result["understood"])
        self.assertFalse(result["trainable"])
        self.assertFalse(result["execution_enabled"])
        self.assertEqual("manifest.yaml", result["manifest_path"])
        self.assertEqual("cnn", result["normalized_manifest"]["model"]["architecture"])
        self.assertIn("train/loss", result["normalized_manifest"]["metrics"]["required"])

    def test_missing_manifest_returns_invalid_contract_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "missing_manifest.zip"
            with zipfile.ZipFile(package_path, "w") as zf:
                zf.writestr("train.py", "def train():\n    return {}\n")

            result = CustomModelPackageValidator.validate_zip(package_path)

        self.assertEqual("invalid_manifest", result["status"])
        self.assertFalse(result["understood"])
        self.assertTrue(any("Manifest not found" in error for error in result["errors"]))
        self.assertFalse(result["execution_enabled"])

    def test_path_traversal_entry_is_blocked_without_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            package_path = Path(tmp) / "unsafe.zip"
            with zipfile.ZipFile(package_path, "w") as zf:
                zf.writestr("../evil.py", "print('no extraction')")
                zf.writestr("manifest.yaml", VALID_MANIFEST)
                zf.writestr("train.py", "def train():\n    return {}\n")
                zf.writestr("predict.py", "def predict():\n    return {}\n")

            result = CustomModelPackageValidator.validate_zip(package_path)

        self.assertEqual("blocked", result["status"])
        self.assertTrue(result["blocked_reasons"])
        self.assertFalse(result["execution_enabled"])


if __name__ == "__main__":
    unittest.main()
