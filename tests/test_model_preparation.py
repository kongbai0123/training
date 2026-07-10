import hashlib
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import app
from src.model_install_manager import ModelInstallManager
from src.model_recommendation import annotate_hardware_fit


class _MemoryResponse:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


class ModelPreparationTests(unittest.TestCase):
    def test_hardware_recommendation_marks_fitting_model(self):
        capabilities = {
            "gpu": {"cuda_available": True, "devices": [{"vram_total_mb": 12288}]},
            "memory": {"total_gb": 32},
            "disk": {"available_gb": 100},
        }
        models = annotate_hardware_fit([
            {
                "model_id": "small",
                "installation_required": True,
                "min_vram_mb": 6144,
                "download_size": 20_000_000,
            },
            {
                "model_id": "oversized",
                "installation_required": True,
                "min_vram_mb": 16384,
                "download_size": 20_000_000,
            },
        ], capabilities)

        self.assertEqual(models[0]["hardware_fit"], "recommended")
        self.assertEqual(models[1]["hardware_fit"], "not_recommended")
        self.assertIn("insufficient_vram", models[1]["hardware_reasons"])

    def test_installer_verifies_checksum_and_replaces_atomically(self):
        payload = b"verified-model-payload"
        checksum = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ModelInstallManager(
                models_dir=Path(temp_dir),
                opener=lambda request, timeout: _MemoryResponse(payload),
            )
            job = manager.start({
                "model_id": "builtin.test",
                "display_name": "Test model",
                "weight": "test.pt",
                "download_url": "https://github.com/example/test.pt",
                "sha256": checksum,
                "download_size": len(payload),
            }, background=False)

            self.assertEqual(job["status"], "completed")
            self.assertEqual((Path(temp_dir) / "test.pt").read_bytes(), payload)
            self.assertFalse((Path(temp_dir) / "test.pt.part").exists())

    def test_installer_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ModelInstallManager(
                models_dir=Path(temp_dir),
                opener=lambda request, timeout: _MemoryResponse(b"unexpected"),
            )
            job = manager.start({
                "model_id": "builtin.test",
                "display_name": "Test model",
                "weight": "test.pt",
                "download_url": "https://github.com/example/test.pt",
                "sha256": "0" * 64,
            }, background=False)

            self.assertEqual(job["status"], "failed")
            self.assertIn("checksum", job["error"].lower())
            self.assertFalse((Path(temp_dir) / "test.pt").exists())

    def test_installer_rejects_unapproved_host(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = ModelInstallManager(models_dir=Path(temp_dir))
            with self.assertRaisesRegex(ValueError, "approved HTTPS host"):
                manager.start({
                    "model_id": "builtin.test",
                    "weight": "test.pt",
                    "download_url": "https://example.com/test.pt",
                }, background=False)

    def test_installer_blocks_duplicate_active_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            gate = threading.Event()

            def opener(request, timeout):
                gate.wait(timeout=1)
                return _MemoryResponse(b"payload")

            manager = ModelInstallManager(models_dir=Path(temp_dir), opener=opener)
            model = {
                "model_id": "builtin.test",
                "weight": "test.pt",
                "download_url": "https://github.com/example/test.pt",
            }
            job = None
            try:
                job = manager.start(model, background=True)
                with self.assertRaisesRegex(ValueError, "active installation"):
                    manager.start(model, background=True)
            finally:
                gate.set()
                if job:
                    for _ in range(100):
                        if manager.get(job["job_id"])["status"] in {"completed", "failed", "cancelled"}:
                            break
                        time.sleep(0.01)


class ModelPreparationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_catalog_includes_hardware_fit(self):
        response = self.client.get("/api/models/catalog?usage=all")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all("hardware_fit" in item for item in response.json()["models"]))

    def test_install_requires_explicit_confirmation(self):
        response = self.client.post("/api/models/install", json={
            "model_id": "builtin.yolov8s-det",
            "confirm": False,
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("explicit confirmation", response.json()["error"]["message"])

    def test_confirmed_install_starts_catalog_model(self):
        fake_job = {"job_id": "model_install_test", "status": "queued"}
        with patch("src.api.routes.models.MODEL_INSTALL_MANAGER.start", return_value=fake_job) as start:
            response = self.client.post("/api/models/install", json={
                "model_id": "builtin.yolov8s-det",
                "confirm": True,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), fake_job)
        self.assertEqual(start.call_args.args[0]["model_id"], "builtin.yolov8s-det")


if __name__ == "__main__":
    unittest.main()
