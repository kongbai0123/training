import hashlib
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from src.model_system.install_state import resolve_builtin_install_state
from src.system_capabilities import get_system_capabilities


class ModelInstallStateTests(unittest.TestCase):
    def test_missing_builtin_weight_is_not_installed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model = resolve_builtin_install_state(
                {
                    "model_id": "builtin.test",
                    "source": "builtin",
                    "format": "pt",
                    "weight": "missing.pt",
                    "trainable": True,
                },
                models_dir=Path(temp_dir),
            )

        self.assertEqual(model["status"], "not_installed")
        self.assertFalse(model["installed"])
        self.assertFalse(model["usable"])
        self.assertTrue(model["installation_required"])

    def test_builtin_weight_checksum_controls_usability(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            weight = root / "model.pt"
            weight.write_bytes(b"known-model-content")
            checksum = hashlib.sha256(weight.read_bytes()).hexdigest()

            verified = resolve_builtin_install_state(
                {
                    "model_id": "builtin.test",
                    "source": "builtin",
                    "format": "pt",
                    "weight": weight.name,
                    "sha256": checksum,
                },
                models_dir=root,
            )
            corrupt = resolve_builtin_install_state(
                {
                    "model_id": "builtin.test",
                    "source": "builtin",
                    "format": "pt",
                    "weight": weight.name,
                    "sha256": "0" * 64,
                },
                models_dir=root,
            )

        self.assertEqual(verified["integrity"], "verified")
        self.assertTrue(verified["usable"])
        self.assertEqual(corrupt["status"], "corrupt")
        self.assertFalse(corrupt["usable"])

    def test_rnn_template_requires_no_installation(self):
        model = resolve_builtin_install_state({
            "model_id": "template.rnn.lstm",
            "source": "template",
            "format": "template",
            "status": "available",
            "trainable": True,
            "training_enabled": True,
        })

        self.assertFalse(model["installation_required"])
        self.assertTrue(model["installed"])
        self.assertTrue(model["usable"])
        self.assertEqual(model["integrity"], "not_applicable")


class SystemCapabilitiesContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_capability_service_has_required_sections(self):
        payload = get_system_capabilities()
        self.assertEqual(set(payload), {"platform", "cpu", "memory", "disk", "gpu", "runtime"})
        self.assertIn("logical_cores", payload["cpu"])
        self.assertIn("available_gb", payload["memory"])
        self.assertIn("available_gb", payload["disk"])
        self.assertIn("cuda_available", payload["gpu"])
        self.assertIn("opencv", payload["runtime"])

    def test_system_capabilities_endpoint_needs_no_project(self):
        response = self.client.get("/api/system/capabilities")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("gpu", payload)
        self.assertIn("disk", payload)

    def test_global_model_catalog_reports_real_install_state(self):
        response = self.client.get("/api/models/catalog?usage=all")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("hardware", payload)
        self.assertGreater(payload["summary"]["total"], 0)
        by_id = {item["model_id"]: item for item in payload["models"]}
        self.assertIn("builtin.yolov8n-seg", by_id)
        self.assertIn(by_id["builtin.yolov8n-seg"]["install_state"], {"available", "not_installed", "corrupt"})
        self.assertFalse(by_id["template.rnn.lstm-classifier"]["installation_required"])


if __name__ == "__main__":
    unittest.main()
